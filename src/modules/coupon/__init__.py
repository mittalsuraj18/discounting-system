"""Coupon module."""

from src.modules.coupon.models import Coupon, UserCoupon, UserCouponStatus
from src.modules.coupon.repository import CouponRepository
from src.modules.coupon.service import CouponService, ValidationResult
from src.modules.coupon.deps import get_coupon_repository, get_coupon_service
from src.modules.coupon.routes import router

__all__ = [
    "Coupon",
    "UserCoupon",
    "UserCouponStatus",
    "CouponRepository",
    "CouponService",
    "ValidationResult",
    "get_coupon_repository",
    "get_coupon_service",
    "router",
]
