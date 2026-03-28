"""Coupon ORM models using SQLAlchemy 2.0 declarative style."""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import ForeignKey, String, Integer, DateTime, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class UserCouponStatus(str, PyEnum):
    """User coupon status enum."""
    HELD = "held"
    USED = "used"
    EXPIRED = "expired"


class Coupon(Base):
    """Coupon model representing a discount coupon."""
    
    __tablename__ = "coupons"
    __table_args__ = {"schema": "coupons"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False
    )
    max_uses: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1
    )
    current_uses: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    user_coupons: Mapped[list["UserCoupon"]] = relationship(
        "UserCoupon",
        back_populates="coupon",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    @property
    def has_available_uses(self) -> bool:
        """Check if coupon has remaining uses."""
        return self.current_uses < self.max_uses
    
    @property
    def is_valid_now(self) -> bool:
        """Check if coupon is currently valid based on dates and active status."""
        now = datetime.utcnow()
        return self.is_active and self.valid_from <= now <= self.valid_until


class UserCoupon(Base):
    """UserCoupon model representing a coupon held or used by a user."""
    
    __tablename__ = "user_coupons"
    __table_args__ = {"schema": "coupons"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    coupon_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coupons.coupons.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    status: Mapped[UserCouponStatus] = mapped_column(
        Enum(UserCouponStatus, name="user_coupon_status", schema="coupons"),
        default=UserCouponStatus.HELD,
        nullable=False
    )
    
    # Relationships
    coupon: Mapped["Coupon"] = relationship("Coupon", back_populates="user_coupons")
