"""Tests for coupon analytics and cleanup services."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.coupon.analytics import (
    CouponAnalyticsService,
    CouponUsageStats,
    AnalyticsSummary,
)
from src.modules.coupon.cleanup import CouponCleanupService
from src.modules.coupon.models import UserCouponStatus


class MockCoupon:
    """Mock coupon for testing analytics."""

    def __init__(
        self,
        code: str,
        max_uses: int,
        current_uses: int,
        is_active: bool = True,
        valid_until=None,
    ):
        self.id = uuid.uuid4()
        self.code = code
        self.max_uses = max_uses
        self.current_uses = current_uses
        self.is_active = is_active
        self.valid_from = datetime.utcnow() - timedelta(days=30)
        self.valid_until = valid_until or datetime.utcnow() + timedelta(days=30)
        self.created_at = datetime.utcnow() - timedelta(days=15)

    @property
    def is_valid_now(self):
        now = datetime.utcnow()
        return self.is_active and self.valid_from <= now <= self.valid_until


class MockUserCoupon:
    """Mock user coupon for testing cleanup."""

    def __init__(self, coupon_id, user_id, status, acquired_at=None):
        self.id = uuid.uuid4()
        self.coupon_id = coupon_id
        self.user_id = user_id
        self.status = status
        self.acquired_at = acquired_at or datetime.utcnow()


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


class TestCouponAnalytics:
    """Tests for CouponAnalyticsService."""

    @pytest.mark.asyncio
    async def test_empty_database_returns_zero_stats(self, mock_db):
        """Empty database should return all-zero analytics."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = CouponAnalyticsService(mock_db)
        summary = await service.get_usage_stats()

        assert summary.total_coupons == 0
        assert summary.active_coupons == 0
        assert summary.expired_coupons == 0
        assert summary.total_redemptions == 0
        assert summary.average_usage_rate == 0.0

    @pytest.mark.asyncio
    async def test_single_active_coupon_stats(self, mock_db):
        """Active coupon should be counted and stats calculated."""
        coupon = MockCoupon("SUMMER20", max_uses=100, current_uses=45)

        mock_coupon_result = MagicMock()
        mock_coupon_result.scalars.return_value.all.return_value = [coupon]

        mock_user_count = MagicMock()
        mock_user_count.scalar.return_value = 30

        mock_db.execute.side_effect = [mock_coupon_result, mock_user_count]

        service = CouponAnalyticsService(mock_db)
        summary = await service.get_usage_stats()

        assert summary.total_coupons == 1
        assert summary.active_coupons == 1
        assert summary.coupon_stats[0].code == "SUMMER20"
        assert summary.coupon_stats[0].unique_users == 30
        assert summary.total_redemptions == 100

    @pytest.mark.asyncio
    async def test_inactive_coupon_counted_as_expired(self, mock_db):
        """Inactive coupons should be counted in expired_coupons."""
        coupon = MockCoupon("OLD10", max_uses=50, current_uses=50, is_active=False)

        mock_coupon_result = MagicMock()
        mock_coupon_result.scalars.return_value.all.return_value = [coupon]

        mock_user_count = MagicMock()
        mock_user_count.scalar.return_value = 40

        mock_db.execute.side_effect = [mock_coupon_result, mock_user_count]

        service = CouponAnalyticsService(mock_db)
        summary = await service.get_usage_stats()

        assert summary.expired_coupons == 1
        assert summary.active_coupons == 0

    @pytest.mark.asyncio
    async def test_top_coupons_sorted_by_usage(self, mock_db):
        """Top coupons should be sorted by total_uses descending."""
        coupons = [
            MockCoupon("LOW", max_uses=100, current_uses=10),
            MockCoupon("HIGH", max_uses=100, current_uses=90),
            MockCoupon("MID", max_uses=100, current_uses=50),
        ]

        mock_coupon_result = MagicMock()
        mock_coupon_result.scalars.return_value.all.return_value = coupons

        mock_user_counts = [MagicMock() for _ in range(3)]
        for m in mock_user_counts:
            m.scalar.return_value = 5

        mock_db.execute.side_effect = [mock_coupon_result] + mock_user_counts

        service = CouponAnalyticsService(mock_db)
        summary = await service.get_usage_stats()

        codes = [c.code for c in summary.top_coupons]
        assert codes == ["HIGH", "MID", "LOW"]

    @pytest.mark.asyncio
    async def test_filters_applied_to_query(self, mock_db):
        """Filters should be passed through to the query."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = CouponAnalyticsService(mock_db)
        await service.get_usage_stats({"is_active": True})

        # Verify execute was called (filter was applied)
        mock_db.execute.assert_called_once()


class TestCouponCleanup:
    """Tests for CouponCleanupService."""

    @pytest.mark.asyncio
    async def test_cleanup_releases_expired_holds(self, mock_db):
        """Holds past the timeout should be marked as expired."""
        old_hold = MockUserCoupon(
            coupon_id=uuid.uuid4(),
            user_id="user_1",
            status=UserCouponStatus.HELD,
            acquired_at=datetime.utcnow() - timedelta(hours=2),
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [old_hold]
        mock_db.execute.return_value = mock_result

        service = CouponCleanupService(mock_db)
        count = await service.cleanup_expired_holds()

        assert count == 1
        assert old_hold.status == UserCouponStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_cleanup_no_expired_holds(self, mock_db):
        """No expired holds should return zero."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = CouponCleanupService(mock_db)
        count = await service.cleanup_expired_holds()

        assert count == 0
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_purge_removes_old_records(self, mock_db):
        """Old USED/EXPIRED records should be purged."""
        mock_result = MagicMock()
        mock_result.rowcount = 15
        mock_db.execute.return_value = mock_result

        service = CouponCleanupService(mock_db)
        count = await service.purge_old_usage_records(retention_days=90)

        assert count == 15

    @pytest.mark.asyncio
    async def test_purge_nothing_to_delete(self, mock_db):
        """No old records should return zero without flushing."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        service = CouponCleanupService(mock_db)
        count = await service.purge_old_usage_records()

        assert count == 0
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_summary_returns_counts(self, mock_db):
        """Cleanup summary should return counts for all categories."""
        mock_results = []
        for val in [3, 7, 12]:
            m = MagicMock()
            m.scalar.return_value = val
            mock_results.append(m)

        mock_db.execute.side_effect = mock_results

        service = CouponCleanupService(mock_db)
        summary = await service.get_cleanup_summary()

        assert summary == {
            "expired_holds": 3,
            "expired_coupons": 7,
            "old_records": 12,
        }
