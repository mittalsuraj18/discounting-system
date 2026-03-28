"""Checkout ORM models using SQLAlchemy 2.0 declarative style."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any

from sqlalchemy import ForeignKey, String, DateTime, Numeric, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class OrderStatus(str, PyEnum):
    """Order status enum."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PAID = "paid"
    CANCELLED = "cancelled"


class CheckoutStatus(str, PyEnum):
    """Checkout session status enum."""
    INITIATED = "initiated"
    COUPON_APPLIED = "coupon_applied"
    PAYMENT_PENDING = "payment_pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Order(Base):
    """Order model representing a checkout order."""
    
    __tablename__ = "orders"
    __table_args__ = {"schema": "checkout"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", schema="checkout"),
        default=OrderStatus.PENDING,
        nullable=False
    )
    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )
    discount_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    checkout_session: Mapped[Optional["CheckoutSession"]] = relationship(
        "CheckoutSession",
        back_populates="order",
        uselist=False,
        lazy="selectin"
    )


class CheckoutSession(Base):
    """CheckoutSession model representing a checkout flow."""
    
    __tablename__ = "checkout_sessions"
    __table_args__ = {"schema": "checkout"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("checkout.orders.id", ondelete="CASCADE"),
        nullable=False
    )
    status: Mapped[CheckoutStatus] = mapped_column(
        Enum(CheckoutStatus, name="checkout_status", schema="checkout"),
        default=CheckoutStatus.INITIATED,
        nullable=False
    )
    held_coupons: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False
    )
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.utcnow() + timedelta(minutes=30),
        nullable=False
    )
    
    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="checkout_session")
