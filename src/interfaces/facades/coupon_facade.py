"""Coupon facade implementation for cross-module communication."""
import uuid
from typing import Any, List

from src.modules.coupon.service import CouponService
from src.modules.coupon.models import Coupon


class CouponFacade:
    """Concrete implementation of coupon facade for checkout module integration."""
    
    def __init__(self, coupon_service: CouponService):
        self._service = coupon_service
    
    async def validate(self, code: str, cart: Any) -> Coupon | None:
        """Validate a coupon code for a cart.
        
        Returns the coupon if valid, None otherwise.
        """
        # Extract user_id from cart if available
        user_id = getattr(cart, 'user_id', 'anonymous')
        cart_id = getattr(cart, 'id', uuid.uuid4())
        
        result = await self._service.validate(code, user_id, cart_id)
        return result.coupon if result.valid else None
    
    async def hold(self, coupon_ids: List[uuid.UUID], order_id: uuid.UUID) -> bool:
        """Hold coupons for an order."""
        try:
            await self._service.hold(coupon_ids, order_id)
            return True
        except Exception:
            return False
    
    async def release(self, coupon_ids: List[uuid.UUID], order_id: uuid.UUID) -> bool:
        """Release held coupons for an order."""
        try:
            await self._service.release_hold(order_id)
            return True
        except Exception:
            return False


# For backward compatibility
ICouponService = CouponFacade
