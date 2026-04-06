"""Expired coupon cleanup service."""

import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.coupon.models import Coupon, UserCoupon, UserCouponStatus

logger = logging.getLogger(__name__)


class CouponCleanupService:
    """Service for cleaning up expired coupons and stale hold records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def cleanup_expired_holds(
        self,
        hold_timeout_minutes: int = 30
    ) -> int:
        """Release coupon holds that have exceeded the timeout period.

        Holds are created when a user starts checkout. If checkout is not
        completed within the timeout, the hold should be released so
        others can use the coupon.

        Args:
            hold_timeout_minutes: Minutes after which a hold expires

        Returns:
            Number of holds released
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=hold_timeout_minutes)

        query = select(UserCoupon).where(
            UserCoupon.status == UserCouponStatus.HELD,
            UserCoupon.acquired_at < cutoff_time
        )

        result = await self.db.execute(query)
        expired_holds = result.scalars().all()

        released_count = 0
        for hold in expired_holds:
            hold.status = UserCouponStatus.EXPIRED
            released_count += 1
            logger.info(
                f"Released expired hold: coupon={hold.coupon_id}, user={hold.user_id}"
            )

        if released_count > 0:
            await self.db.flush()

        return released_count

    async def deactivate_expired_coupons(self) -> List[str]:
        """Deactivate coupons that have passed their valid_until date.

        Scans for active coupons whose validity period has ended and
        marks them as inactive to prevent further use.

        Returns:
            List of deactivated coupon codes
        """
        now = datetime.utcnow()

        query = select(Coupon).where(
            Coupon.is_active == True,
            Coupon.valid_until > now
        )

        result = await self.db.execute(query)
        expired_coupons = result.scalars().all()

        deactivated_codes = []
        for coupon in expired_coupons:
            coupon.is_active = False
            deactivated_codes.append(coupon.code)

        if len(deactivated_codes) > 0:
            await self.db.flush()
            logger.info(
                f"Deactivated {len(deactivated_codes)} expired coupons: "
                f"{deactivated_codes}"
            )

        return deactivated_codes

    async def purge_old_usage_records(
        self,
        retention_days: int = 90
    ) -> int:
        """Delete usage records older than the retention period.

        Only removes records in terminal states (USED or EXPIRED),
        never active HELD records.

        Args:
            retention_days: Number of days to retain records

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        query = delete(UserCoupon).where(
            UserCoupon.status.in_([
                UserCouponStatus.USED,
                UserCouponStatus.EXPIRED
            ]),
            UserCoupon.acquired_at < cutoff_date
        )

        result = await self.db.execute(query)
        deleted_count = result.rowcount

        if deleted_count > 0:
            await self.db.flush()
            logger.info(f"Purged {deleted_count} old usage records")

        return deleted_count

    async def get_cleanup_summary(self) -> dict:
        """Get a summary of what would be cleaned up (dry run).

        Returns:
            Dict with counts of items that would be affected
        """
        now = datetime.utcnow()
        hold_cutoff = now - timedelta(minutes=30)
        purge_cutoff = now - timedelta(days=90)

        hold_query = select(func.count()).select_from(UserCoupon).where(
            UserCoupon.status == UserCouponStatus.HELD,
            UserCoupon.acquired_at < hold_cutoff
        )

        expired_query = select(func.count()).select_from(Coupon).where(
            Coupon.is_active == True,
            Coupon.valid_until < now
        )

        old_query = select(func.count()).select_from(UserCoupon).where(
            UserCoupon.status.in_([
                UserCouponStatus.USED,
                UserCouponStatus.EXPIRED
            ]),
            UserCoupon.acquired_at < purge_cutoff
        )

        try:
            hold_result = await self.db.execute(hold_query)
            expired_result = await self.db.execute(expired_query)
            old_result = await self.db.execute(old_query)

            return {
                "expired_holds": hold_result.scalar() or 0,
                "expired_coupons": expired_result.scalar() or 0,
                "old_records": old_result.scalar() or 0
            }
        except Exception:
            pass
