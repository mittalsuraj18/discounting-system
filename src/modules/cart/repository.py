"""Cart repository for database operations."""

import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.cart.models import Cart, CartItem, CartStatus


class CartRepository:
    """Repository for cart database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, cart_id: uuid.UUID | str) -> Optional[Cart]:
        """Get cart by ID with items."""
        if isinstance(cart_id, str):
            cart_id = uuid.UUID(cart_id)
        
        result = await self.db.execute(
            select(Cart).where(Cart.id == cart_id)
        )
        cart = result.scalar_one_or_none()
        
        if cart is None:
            raise NotFoundError("Cart", str(cart_id))
        
        return cart
    
    async def create(
        self,
        user_id: str,
        items: List[CartItem]
    ) -> Cart:
        """Create a new cart with items."""
        cart = Cart(
            id=uuid.uuid4(),
            user_id=user_id,
            status=CartStatus.active,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            items=items
        )
        
        self.db.add(cart)
        await self.db.flush()
        await self.db.refresh(cart)
        
        return cart
    
    async def delete(self, cart_id: uuid.UUID | str) -> None:
        """Delete cart by ID."""
        if isinstance(cart_id, str):
            cart_id = uuid.UUID(cart_id)
        
        result = await self.db.execute(
            select(Cart).where(Cart.id == cart_id)
        )
        cart = result.scalar_one_or_none()
        
        if cart is None:
            raise NotFoundError("Cart", str(cart_id))
        
        await self.db.delete(cart)
        await self.db.flush()
