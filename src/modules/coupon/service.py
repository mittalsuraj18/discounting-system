"""Coupon service for business logic."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.core.exceptions import CouponError, ValidationError
from src.modules.coupon.models import Coupon, UserCoupon, UserCouponStatus
from src.modules.coupon.repository import CouponRepository


@dataclass
class ValidationResult:
    """Result of coupon validation."""
    valid: bool
    coupon: Optional[Coupon]
    discount_value: Decimal
    message: str


class CouponService:
    """Service for coupon business logic."""
    
    def __init__(self, repository: CouponRepository):
        self.repository = repository
    
    async def validate(
        self,
        code: str,
        user_id: str,
        cart_id: uuid.UUID
    ) -> ValidationResult:
        """Validate a coupon code for a user and cart."""
        coupon = await self.repository.get_by_code(code)
        
        if coupon is None:
            return ValidationResult(
                valid=False,
                coupon=None,
                discount_value=Decimal("0"),
                message="Coupon not found"
            )
        
        if not coupon.is_active:
            return ValidationResult(
                valid=False,
                coupon=coupon,
                discount_value=Decimal("0"),
                message="Coupon is inactive"
            )
        
        now = datetime.utcnow()
        if now < coupon.valid_from:
            return ValidationResult(
                valid=False,
                coupon=coupon,
                discount_value=Decimal("0"),
                message="Coupon is not yet valid"
            )
        
        if now > coupon.valid_until:
            return ValidationResult(
                valid=False,
                coupon=coupon,
                discount_value=Decimal("0"),
                message="Coupon has expired"
            )
        
        if not coupon.has_available_uses:
            return ValidationResult(
                valid=False,
                coupon=coupon,
                discount_value=Decimal("0"),
                message="Coupon usage limit reached"
            )
        
        # TODO: Calculate actual discount based on rules engine
        discount_value = Decimal("0")
        
        return ValidationResult(
            valid=True,
            coupon=coupon,
            discount_value=discount_value,
            message="Coupon is valid"
        )
    
    async def create_coupon(self, config: dict) -> Coupon:
        """Create a new coupon with validation."""
        # Validate date ranges
        valid_from = config.get("valid_from")
        valid_until = config.get("valid_until")
        
        if valid_from and valid_until and valid_from >= valid_until:
            raise ValidationError("valid_from must be before valid_until")
        
        if config.get("max_uses", 1) < 1:
            raise ValidationError("max_uses must be at least 1")
        
        if not config.get("code"):
            raise ValidationError("code is required")
        
        # Check for existing coupon with same code (case-insensitive)
        existing = await self.repository.get_by_code(config["code"])
        if existing:
            raise ValidationError(f"Coupon with code '{config['code']}' already exists")
        
        return await self.repository.create(config)
    
    async def hold(self, coupon_ids: list[uuid.UUID], order_id: uuid.UUID) -> list[UserCoupon]:
        """Hold coupons for an order (user_id extracted from order context)."""
        held_coupons = []
        
        for coupon_id in coupon_ids:
            # Verify coupon exists and is valid
            coupon = await self.repository.get_by_id(coupon_id)
            
            if not coupon.is_valid_now or not coupon.has_available_uses:
                raise CouponError(f"Coupon {coupon_id} is not available for hold")
            
            # TODO: Get user_id from order context
            user_id = str(order_id)  # Placeholder - should come from order
            
            user_coupon = await self.repository.hold_coupon(coupon_id, user_id)
            held_coupons.append(user_coupon)
        
        return held_coupons
    
    async def release_hold(self, order_id: uuid.UUID) -> None:
        """Release held coupons for an order."""
        # TODO: Find and delete user_coupons held for this order
        # This requires tracking order_id in UserCoupon or a separate hold table
        pass

    async def bulk_validate(
        self,
        codes: list[str],
        user_id: str,
        cart_id: uuid.UUID
    ) -> dict[str, ValidationResult]:
        """Validate multiple coupon codes at once.

        Useful for checkout flows where multiple coupons may be applied.
        Returns a dict mapping each code to its validation result.
        """
        results = {}

        for code in codes:
            result = self.validate(code, user_id, cart_id)
            results[code] = result

        return results

    async def increment_usage(self, coupon_id: uuid.UUID) -> bool:
        """Increment the usage counter for a coupon.

        Called after successful checkout to record that a coupon was used.

        Returns:
            True if usage was incremented, False if limit already reached
        """
        coupon = await self.repository.get_by_id(coupon_id)

        if coupon.current_uses >= coupon.max_uses:
            return False

        await self.repository.update_uses(coupon_id)
        return True

    def get_coupon_status(self, coupon: Coupon) -> str:
        """Get human-readable status string for a coupon.

        Status can be: active, inactive, scheduled, expired, exhausted, unknown.
        """
        if coupon == None:
            return "unknown"

        if coupon.is_active == False:
            return "inactive"

        now = datetime.utcnow()
        if now < coupon.valid_from:
            return "scheduled"
        elif now > coupon.valid_until:
            return "expired"
        elif coupon.has_available_uses == False:
            return "exhausted"

        return "active"
