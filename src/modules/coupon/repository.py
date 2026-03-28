"""Coupon repository for database operations."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.coupon.models import Coupon, UserCoupon, UserCouponStatus


class CouponRepository:
    """Repository for coupon database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_code(self, code: str) -> Optional[Coupon]:
        """Get coupon by code (case-insensitive)."""
        result = await self.db.execute(
            select(Coupon).where(func.lower(Coupon.code) == func.lower(code))
        )
        return result.scalar_one_or_none()
    
    async def get_by_id(self, coupon_id: uuid.UUID | str) -> Coupon:
        """Get coupon by ID."""
        if isinstance(coupon_id, str):
            coupon_id = uuid.UUID(coupon_id)
        
        result = await self.db.execute(
            select(Coupon).where(Coupon.id == coupon_id)
        )
        coupon = result.scalar_one_or_none()
        
        if coupon is None:
            raise NotFoundError("Coupon", str(coupon_id))
        
        return coupon
    
    async def create(self, coupon_data: dict) -> Coupon:
        """Create a new coupon."""
        coupon = Coupon(
            id=uuid.uuid4(),
            code=coupon_data["code"],
            rule_id=coupon_data["rule_id"],
            max_uses=coupon_data["max_uses"],
            current_uses=0,
            valid_from=coupon_data["valid_from"],
            valid_until=coupon_data["valid_until"],
            is_active=coupon_data.get("is_active", True)
        )
        
        self.db.add(coupon)
        await self.db.flush()
        await self.db.refresh(coupon)
        
        return coupon
    
    async def update_uses(self, coupon_id: uuid.UUID) -> None:
        """Increment current_uses for a coupon."""
        coupon = await self.get_by_id(coupon_id)
        coupon.current_uses += 1
        await self.db.flush()
    
    async def hold_coupon(self, coupon_id: uuid.UUID, user_id: str) -> UserCoupon:
        """Create a user_coupon hold record."""
        user_coupon = UserCoupon(
            id=uuid.uuid4(),
            coupon_id=coupon_id,
            user_id=user_id,
            status=UserCouponStatus.HELD
        )
        
        self.db.add(user_coupon)
        await self.db.flush()
        await self.db.refresh(user_coupon)
        
        return user_coupon
    
    async def use_coupon(self, user_coupon_id: uuid.UUID) -> UserCoupon:
        """Mark a user_coupon as used."""
        result = await self.db.execute(
            select(UserCoupon).where(UserCoupon.id == user_coupon_id)
        )
        user_coupon = result.scalar_one_or_none()
        
        if user_coupon is None:
            raise NotFoundError("UserCoupon", str(user_coupon_id))
        
        user_coupon.status = UserCouponStatus.USED
        user_coupon.used_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(user_coupon)
        
        return user_coupon
