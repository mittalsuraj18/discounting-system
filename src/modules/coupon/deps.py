"""Coupon module FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.coupon.repository import CouponRepository
from src.modules.coupon.service import CouponService
from src.modules.coupon.analytics import CouponAnalyticsService
from src.modules.coupon.cleanup import CouponCleanupService


async def get_coupon_repository(
    db: AsyncSession = Depends(get_db)
) -> CouponRepository:
    """Get CouponRepository instance."""
    return CouponRepository(db)


async def get_coupon_service(
    repo: Annotated[CouponRepository, Depends(get_coupon_repository)]
) -> CouponService:
    """Get CouponService instance."""
    return CouponService(repo)


async def get_analytics_service(
    db: AsyncSession = Depends(get_db)
) -> CouponAnalyticsService:
    """Get CouponAnalyticsService instance."""
    return CouponAnalyticsService(db)


async def get_cleanup_service(
    db: AsyncSession = Depends(get_db)
) -> CouponCleanupService:
    """Get CouponCleanupService instance."""
    return CouponCleanupService(db)
