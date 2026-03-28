"""Cart ORM models using SQLAlchemy 2.0 declarative style."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List

from sqlalchemy import ForeignKey, String, Integer, DateTime, Numeric, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class CartStatus(str, PyEnum):
    """Cart status enum."""
    active = "active"
    checkout = "checkout"
    expired = "expired"


class Cart(Base):
    """Cart model representing a shopping cart."""
    
    __tablename__ = "carts"
    __table_args__ = {"schema": "cart"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CartStatus] = mapped_column(
        Enum(CartStatus, name="cart_status", schema="cart"),
        default=CartStatus.active,
        nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.utcnow() + timedelta(hours=1),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    items: Mapped[List["CartItem"]] = relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class CartItem(Base):
    """CartItem model representing an item in a cart."""
    
    __tablename__ = "cart_items"
    __table_args__ = {"schema": "cart"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    cart_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cart.carts.id", ondelete="CASCADE"),
        nullable=False
    )
    product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )
    
    # Relationships
    cart: Mapped["Cart"] = relationship("Cart", back_populates="items")
    
    @property
    def subtotal(self) -> Decimal:
        """Calculate subtotal for this item."""
        return self.unit_price * self.quantity
