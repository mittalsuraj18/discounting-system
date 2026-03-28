"""Rules ORM models for rule engine."""

import uuid
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import ForeignKey, String, Integer, Numeric, Enum, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class ConditionType(str, PyEnum):
    """Condition type enum."""
    cart_total = "cart_total"
    item_count = "item_count"
    product_id = "product_id"
    category = "category"
    user_segment = "user_segment"


class Operator(str, PyEnum):
    """Comparison operator enum."""
    eq = "eq"
    gt = "gt"
    lt = "lt"
    gte = "gte"
    lte = "lte"
    in_op = "in"
    not_in = "not_in"
    contains = "contains"


class ActionType(str, PyEnum):
    """Action type enum."""
    percent = "percent"
    flat = "flat"
    item = "item"


class ActionTarget(str, PyEnum):
    """Action target enum."""
    total = "total"
    item = "item"
    shipping = "shipping"


class Rule(Base):
    """Rule model representing a discount rule."""
    
    __tablename__ = "rules"
    __table_args__ = {"schema": "rules"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        comment="Lower number = higher priority (1 runs before 10)"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    
    # Relationships
    conditions: Mapped[List["Condition"]] = relationship(
        "Condition",
        back_populates="rule",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    actions: Mapped[List["Action"]] = relationship(
        "Action",
        back_populates="rule",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class Condition(Base):
    """Condition model representing a rule condition."""
    
    __tablename__ = "conditions"
    __table_args__ = {"schema": "rules"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.rules.id", ondelete="CASCADE"),
        nullable=False
    )
    type: Mapped[ConditionType] = mapped_column(
        Enum(ConditionType, name="condition_type", schema="rules"),
        nullable=False
    )
    operator: Mapped[Operator] = mapped_column(
        Enum(Operator, name="operator_type", schema="rules"),
        nullable=False
    )
    field: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON value stored as string"
    )
    
    # Relationships
    rule: Mapped["Rule"] = relationship("Rule", back_populates="conditions")


class Action(Base):
    """Action model representing a rule action (discount)."""
    
    __tablename__ = "actions"
    __table_args__ = {"schema": "rules"}
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rules.rules.id", ondelete="CASCADE"),
        nullable=False
    )
    type: Mapped[ActionType] = mapped_column(
        Enum(ActionType, name="action_type", schema="rules"),
        nullable=False
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Discount value (percent, flat amount, or item quantity)"
    )
    target: Mapped[ActionTarget] = mapped_column(
        Enum(ActionTarget, name="action_target", schema="rules"),
        nullable=False,
        default=ActionTarget.total
    )
    max_discount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Maximum discount cap"
    )
    
    # Relationships
    rule: Mapped["Rule"] = relationship("Rule", back_populates="actions")
