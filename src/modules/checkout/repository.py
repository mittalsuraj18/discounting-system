"""Checkout repository for database operations."""

import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.checkout.models import Order, CheckoutSession, OrderStatus, CheckoutStatus


class OrderRepository:
    """Repository for order database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(
        self,
        cart_id: uuid.UUID,
        user_id: str,
        total: Decimal,
        discount_total: Decimal
    ) -> Order:
        """Create a new order."""
        order = Order(
            id=uuid.uuid4(),
            cart_id=cart_id,
            user_id=user_id,
            status=OrderStatus.PENDING,
            total=total,
            discount_total=discount_total,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.db.add(order)
        await self.db.flush()
        await self.db.refresh(order)
        
        return order
    
    async def get_by_id(self, order_id: uuid.UUID | str) -> Order:
        """Get order by ID."""
        if isinstance(order_id, str):
            order_id = uuid.UUID(order_id)
        
        result = await self.db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if order is None:
            raise NotFoundError("Order", str(order_id))
        
        return order
    
    async def update_status(
        self,
        order_id: uuid.UUID | str,
        status: OrderStatus
    ) -> Order:
        """Update order status."""
        order = await self.get_by_id(order_id)
        order.status = status
        order.updated_at = datetime.utcnow()
        
        await self.db.flush()
        await self.db.refresh(order)
        
        return order


class CheckoutSessionRepository:
    """Repository for checkout session database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create(self, order_id: uuid.UUID) -> CheckoutSession:
        """Create a new checkout session."""
        session = CheckoutSession(
            id=uuid.uuid4(),
            order_id=order_id,
            status=CheckoutStatus.INITIATED,
            held_coupons=[],
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + datetime.timedelta(minutes=30)
        )
        
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        
        return session
    
    async def get_by_id(self, session_id: uuid.UUID | str) -> CheckoutSession:
        """Get checkout session by ID."""
        if isinstance(session_id, str):
            session_id = uuid.UUID(session_id)
        
        result = await self.db.execute(
            select(CheckoutSession).where(CheckoutSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        if session is None:
            raise NotFoundError("CheckoutSession", str(session_id))
        
        return session
    
    async def update_status(
        self,
        session_id: uuid.UUID | str,
        status: CheckoutStatus
    ) -> CheckoutSession:
        """Update checkout session status."""
        session = await self.get_by_id(session_id)
        session.status = status
        
        await self.db.flush()
        await self.db.refresh(session)
        
        return session
    
    async def update_held_coupons(
        self,
        session_id: uuid.UUID | str,
        coupons: list
    ) -> CheckoutSession:
        """Update held coupons for a session."""
        session = await self.get_by_id(session_id)
        session.held_coupons = coupons
        
        await self.db.flush()
        await self.db.refresh(session)
        
        return session
