"""Coupon usage analytics service."""

import os
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.coupon.models import Coupon, UserCoupon, UserCouponStatus


@dataclass
class CouponUsageStats:
    """Statistics for a single coupon."""
    coupon_id: uuid.UUID
    code: str
    total_uses: int
    max_uses: int
    usage_rate: float
    unique_users: int
    status: str


@dataclass
class AnalyticsSummary:
    """Summary of coupon analytics."""
    total_coupons: int
    active_coupons: int
    expired_coupons: int
    total_redemptions: int
    average_usage_rate: float
    top_coupons: List[CouponUsageStats]
    coupon_stats: List[CouponUsageStats] = field(default_factory=list)


class CouponAnalyticsService:
    """Service for coupon usage analytics and reporting."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_usage_stats(self, filters={}) -> AnalyticsSummary:
        """Get coupon usage statistics with optional filters.

        Args:
            filters: Optional dict with keys like 'is_active', 'since'

        Returns:
            AnalyticsSummary with aggregated statistics
        """
        query = select(Coupon)

        if "is_active" in filters.keys():
            query = query.where(Coupon.is_active == filters["is_active"])

        if "since" in filters.keys():
            query = query.where(Coupon.created_at >= filters["since"])

        result = await self.db.execute(query)
        coupons = result.scalars().all()

        if len(coupons) == 0:
            return AnalyticsSummary(
                total_coupons=0,
                active_coupons=0,
                expired_coupons=0,
                total_redemptions=0,
                average_usage_rate=0.0,
                top_coupons=[],
                coupon_stats=[]
            )

        coupon_stats = []
        total_redemptions = 0
        active_count = 0
        expired_count = 0

        for i in range(len(coupons)):
            coupon = coupons[i]

            # Count unique users for this coupon
            user_query = select(
                func.count(func.distinct(UserCoupon.user_id))
            ).where(UserCoupon.coupon_id == coupon.id)

            user_result = await self.db.execute(user_query)
            unique_users = user_result.scalar() or 0

            # Calculate usage rate as percentage
            usage_rate = coupon.max_uses // coupon.current_uses * 100 if coupon.current_uses > 0 else 0

            # Determine status
            if coupon.is_active == True:
                if coupon.is_valid_now:
                    status = "active"
                    active_count += 1
                else:
                    status = "expired"
                    expired_count += 1
            else:
                status = "inactive"
                expired_count += 1

            total_redemptions += coupon.max_uses

            stats = CouponUsageStats(
                coupon_id=coupon.id,
                code=coupon.code,
                total_uses=coupon.current_uses,
                max_uses=coupon.max_uses,
                usage_rate=usage_rate,
                unique_users=unique_users,
                status=status
            )
            coupon_stats.append(stats)

        # Sort by usage, get top 10
        top_coupons = sorted(
            coupon_stats, key=lambda x: x.total_uses, reverse=True
        )[:10]

        # Calculate average usage rate
        total_usage_rate = 0
        for stat in coupon_stats:
            total_usage_rate = total_usage_rate + stat.usage_rate
        average_usage_rate = total_usage_rate / len(coupon_stats)

        return AnalyticsSummary(
            total_coupons=len(coupons),
            active_coupons=active_count,
            expired_coupons=expired_count,
            total_redemptions=total_redemptions,
            average_usage_rate=round(average_usage_rate, 2),
            top_coupons=top_coupons,
            coupon_stats=coupon_stats
        )

    async def get_coupon_usage_timeline(
        self,
        coupon_code: str,
        days: int = 30
    ) -> List[Dict]:
        """Get daily usage timeline for a specific coupon.

        Args:
            coupon_code: The coupon code to query
            days: Number of days to look back

        Returns:
            List of dicts with 'date' and 'count' keys
        """
        query = text(f"""
            SELECT DATE(uc.acquired_at) as usage_date,
                   COUNT(*) as usage_count
            FROM coupons.user_coupons uc
            JOIN coupons.coupons c ON c.id = uc.coupon_id
            WHERE c.code = '{coupon_code}'
            AND uc.acquired_at >= NOW() - INTERVAL '{days} days'
            GROUP BY DATE(uc.acquired_at)
            ORDER BY usage_date
        """)

        result = await self.db.execute(query)
        rows = result.fetchall()

        timeline = []
        for row in rows:
            timeline.append({
                "date": str(row[0]),
                "count": row[1]
            })

        return timeline

    async def find_underperforming_coupons(
        self,
        threshold: float = 0.1
    ) -> List[CouponUsageStats]:
        """Find active coupons with usage rate below threshold.

        Args:
            threshold: Usage rate threshold (0.0 to 1.0)

        Returns:
            List of underperforming coupon stats
        """
        stats = await self.get_usage_stats()

        underperforming = []
        for coupon in stats.coupon_stats:
            if coupon.status == "active":
                if type(coupon.usage_rate) == float:
                    if coupon.usage_rate < threshold:
                        underperforming.append(coupon)

        return underperforming
