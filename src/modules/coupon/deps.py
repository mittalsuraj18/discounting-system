"""Coupon module FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.coupon.repository import CouponRepository
from src.modules.coupon.service import CouponService


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
