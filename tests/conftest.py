"""Test fixtures for rule engine tests."""
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

import pytest
import pytest_asyncio

from src.modules.cart.models import Cart, CartItem
from src.modules.rules.engine import (
    CouponConfig,
    EvalConfig,
    EvalCategory,
    EvalType,
    FilterConfig,
    EvaluationContext,
    RuleEngine,
)


@dataclass
class MockCartItem:
    """Mock cart item for testing without DB."""
    product_id: str
    quantity: int
    unit_price: Decimal
    categories: List[str] = field(default_factory=list)
    _id: uuid.UUID = field(default_factory=uuid.uuid4)
    
    @property
    def id(self) -> uuid.UUID:
        return self._id
    
    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity
    
    @property
    def cart_id(self) -> uuid.UUID:
        return uuid.uuid4()  # Not used directly
    
    @cart_id.setter
    def cart_id(self, value: uuid.UUID) -> None:
        pass


@dataclass
class MockCart:
    """Mock cart for testing without DB."""
    user_id: str = "test_user"
    items: List[MockCartItem] = field(default_factory=list)
    _id: uuid.UUID = field(default_factory=uuid.uuid4)
    
    @property
    def id(self) -> uuid.UUID:
        return self._id


@pytest.fixture
def cart_factory():
    """Factory for creating mock carts with items.
    
    Usage: cart_factory([{"product_id": "puma-001", "quantity": 2, "unit_price": 100, "categories": ["puma"]}])
    """
    def _create_cart(items_data: List[Dict[str, Any]]) -> MockCart:
        items = []
        for data in items_data:
            item = MockCartItem(
                product_id=data.get("product_id", f"prod-{len(items)}"),
                quantity=data.get("quantity", 1),
                unit_price=Decimal(str(data.get("unit_price", 100))),
                categories=data.get("categories", []),
            )
            items.append(item)
        return MockCart(items=items)
    return _create_cart


@pytest.fixture
def context_factory(cart_factory):
    """Factory for creating evaluation contexts.
    
    Usage: context_factory(cart_items=[{...}], coupons=[], metadata={})
    """
    def _create_context(
        cart_items: List[Dict[str, Any]] = None,
        coupons: List[CouponConfig] = None,
        metadata: Dict[str, Any] = None,
        user_id: str = "test_user",
    ) -> EvaluationContext:
        if cart_items is None:
            cart_items = []
        if coupons is None:
            coupons = []
        if metadata is None:
            metadata = {}
        
        cart = cart_factory(cart_items)
        
        # Build item_categories from cart items for the context
        item_categories = {}
        for item in cart.items:
            item_categories[str(item.id)] = item.categories
        
        # Merge with any provided item_categories
        if "item_categories" in metadata:
            item_categories.update(metadata["item_categories"])
        metadata["item_categories"] = item_categories
        
        return EvaluationContext(
            cart=cart,
            user_id=user_id,
            coupons=coupons,
            metadata=metadata,
        )
    return _create_context


@pytest.fixture
def coupon_factory():
    """Factory for creating coupon configs.
    
    Usage: coupon_factory(
        code="PUMA20",
        filters={"include": ["puma"], "exclude": [], "min_qty": None, "min_value": None},
        eval_config={"category": "item", "type": "percent", "value": 20, "max_value": None},
        stackable=True,
        priority=100
    )
    """
    def _create_coupon(
        code: str = "TEST10",
        filters: Optional[Dict[str, Any]] = None,
        eval_config: Optional[Dict[str, Any]] = None,
        stackable: bool = True,
        priority: int = 100,
    ) -> CouponConfig:
        if filters is None:
            filters = {}
        if eval_config is None:
            eval_config = {}
        
        filter_config = FilterConfig(
            include=filters.get("include", []),
            exclude=filters.get("exclude", []),
            min_qty=filters.get("min_qty"),
            min_value=Decimal(str(filters["min_value"])) if filters.get("min_value") else None,
        )
        
        eval_conf = EvalConfig(
            category=EvalCategory(eval_config.get("category", "total")),
            type=EvalType(eval_config.get("type", "percent")),
            value=Decimal(str(eval_config.get("value", 10))),
            max_value=Decimal(str(eval_config["max_value"])) if eval_config.get("max_value") else None,
        )
        
        return CouponConfig(
            id=uuid.uuid4(),
            name=f"Coupon {code}",
            code=code,
            filters=filter_config,
            eval=eval_conf,
            stackable=stackable,
            priority=priority,
        )
    return _create_coupon


@pytest.fixture
def rule_engine():
    """Create a rule engine instance with mock repository."""
    class MockRepository:
        pass
    
    return RuleEngine(repository=MockRepository())
