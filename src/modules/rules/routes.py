"""Rules API routes with CouponConfig schema support."""
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from src.modules.rules.deps import get_rule_engine, get_rule_repository
from src.modules.rules.engine import (
    RuleEngine, EvaluationContext, DiscountPlan, CouponConfig,
    FilterConfig, EvalConfig, EvalCategory, EvalType, ItemDiscount
)
from src.modules.rules.repository import RuleRepository

router = APIRouter(prefix="/rule", tags=["rules"])


# Pydantic Schemas matching Readme coupon config

class FilterConfigSchema(BaseModel):
    """Filter config schema matching Readme."""
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)
    min_qty: Optional[int] = None
    min_value: Optional[Decimal] = None


class EvalConfigSchema(BaseModel):
    """Eval config schema matching Readme."""
    category: str = Field(default="total", pattern="^(item|total)$")
    type: str = Field(default="percent", pattern="^(percent|flat|sku|item)$")
    value: Decimal = Field(..., gt=0)
    max_value: Optional[Decimal] = None


class CouponConfigSchema(BaseModel):
    """Complete coupon config schema matching Readme."""
    id: Optional[uuid.UUID] = None
    name: str
    code: str
    filters: FilterConfigSchema = Field(default_factory=FilterConfigSchema)
    eval: EvalConfigSchema
    stackable: bool = True
    priority: int = 100


class CartItemSchema(BaseModel):
    """Cart item for evaluation."""
    id: Optional[uuid.UUID] = None
    product_id: str
    quantity: int = Field(..., ge=1)
    unit_price: Decimal = Field(..., gt=0)
    categories: List[str] = Field(default_factory=list)


class EvaluationRequest(BaseModel):
    """Schema for rule evaluation request with full coupon config."""
    user_id: str = Field(..., min_length=1)
    cart_items: List[CartItemSchema] = Field(default_factory=list)
    coupons: List[CouponConfigSchema] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ItemDiscountResponse(BaseModel):
    """Item-level discount breakdown."""
    item_id: str
    item_name: str
    original_price: Decimal
    discount_amount: Decimal
    final_price: Decimal
    applied_by: str


class CouponResultResponse(BaseModel):
    """Individual coupon evaluation result."""
    coupon_id: str
    code: str
    applicable: bool
    reason: str
    discount_total: Decimal
    item_discounts: List[ItemDiscountResponse]


class DiscountPlanResponse(BaseModel):
    """Complete discount plan response."""
    original_total: Decimal
    
    # Stacked calculation
    stacked_discount: Decimal
    stacked_final_total: Decimal
    
    # Unstacked alternatives
    unstacked_alternatives: List[Decimal]
    
    # Final result
    final_discount: Decimal
    final_total: Decimal
    
    # Detailed breakdown
    applied_coupons: List[CouponResultResponse]
    rejected_coupons: List[CouponResultResponse]


# Helper functions

def _convert_schema_to_config(schema: CouponConfigSchema) -> CouponConfig:
    """Convert Pydantic schema to internal CouponConfig."""
    return CouponConfig(
        id=schema.id or uuid.uuid4(),
        name=schema.name,
        code=schema.code,
        filters=FilterConfig(
            include=schema.filters.include,
            exclude=schema.filters.exclude,
            min_qty=schema.filters.min_qty,
            min_value=schema.filters.min_value
        ),
        eval=EvalConfig(
            category=EvalCategory(schema.eval.category),
            type=EvalType(schema.eval.type),
            value=schema.eval.value,
            max_value=schema.eval.max_value
        ),
        stackable=schema.stackable,
        priority=schema.priority
    )


def _convert_item_schema_to_model(item: CartItemSchema) -> Any:
    """Convert CartItemSchema to CartItem model."""
    from src.modules.cart.models import CartItem
    return CartItem(
        id=item.id or uuid.uuid4(),
        product_id=item.product_id,
        quantity=item.quantity,
        unit_price=item.unit_price
    )


def _build_discount_response(plan: DiscountPlan) -> DiscountPlanResponse:
    """Build DiscountPlanResponse from internal DiscountPlan."""
    
    def convert_item_discount(id: ItemDiscount) -> ItemDiscountResponse:
        return ItemDiscountResponse(
            item_id=str(id.item_id),
            item_name=id.item_name,
            original_price=id.original_price,
            discount_amount=id.discount_amount,
            final_price=id.final_price,
            applied_by=id.applied_by
        )
    
    def convert_coupon_result(cr: Any) -> CouponResultResponse:
        return CouponResultResponse(
            coupon_id=str(cr.coupon_id),
            code=cr.code,
            applicable=cr.applicable,
            reason=cr.reason,
            discount_total=cr.discount_total,
            item_discounts=[convert_item_discount(i) for i in (cr.item_discounts or [])]
        )
    
    original_total = plan.final_total + plan.final_discount
    
    return DiscountPlanResponse(
        original_total=original_total,
        stacked_discount=plan.stacked_discount,
        stacked_final_total=plan.stacked_final_total,
        unstacked_alternatives=list(plan.unstacked_alternatives),
        final_discount=plan.final_discount,
        final_total=plan.final_total,
        applied_coupons=[convert_coupon_result(c) for c in plan.applied_coupons],
        rejected_coupons=[convert_coupon_result(c) for c in plan.rejected_coupons]
    )


# Routes

@router.post("/evaluate", response_model=DiscountPlanResponse)
async def evaluate_rules(
    request: EvaluationRequest,
    engine: RuleEngine = Depends(get_rule_engine)
) -> DiscountPlanResponse:
    """
    Evaluate discount rules for given cart and coupons.
    
    Implements the Readme stacking logic:
    - stackable=True: discounts stack (sum)
    - stackable=False: computed individually, max taken
    - Final = max(stacked_discounts, unstacked_1, unstacked_2, ...)
    
    Examples:
    
    **PUMA Buy 1 Get 1:**
    ```json
    {
        "user_id": "user123",
        "cart_items": [
            {"product_id": "puma-shoe-001", "quantity": 2, "unit_price": 100.00, "categories": ["puma"]}
        ],
        "coupons": [
            {
                "name": "puma buy 1 get 1",
                "code": "PUMA_1_1",
                "filters": {"include": ["puma"], "min_qty": 1},
                "eval": {"category": "item", "type": "item", "value": 1},
                "stackable": true,
                "priority": 100
            }
        ]
    }
    ```
    
    **ICICI 10% off (max 500):**
    ```json
    {
        "user_id": "user123",
        "cart_items": [{"product_id": "item-001", "quantity": 1, "unit_price": 2000.00}],
        "coupons": [
            {
                "name": "icici 10% off on 2000 max 500",
                "code": "ICICI_10",
                "filters": {"include": ["icici_credit_card"], "min_value": 2000},
                "eval": {"category": "total", "type": "percent", "value": 10, "max_value": 500},
                "stackable": true,
                "priority": 900
            }
        ],
        "metadata": {"payment_method": "icici_credit_card"}
    }
    ```
    """
    from src.modules.cart.models import Cart
    
    # Build cart items
    cart_items = [_convert_item_schema_to_model(item) for item in request.cart_items]
    
    # Build cart
    cart = Cart(
        id=uuid.uuid4(),
        user_id=request.user_id,
        items=cart_items
    )
    
    # Build coupon configs
    coupon_configs = [_convert_schema_to_config(c) for c in request.coupons]
    
    # Build metadata including item categories
    metadata = dict(request.metadata)
    item_categories = {}
    for item in request.cart_items:
        if item.id:
            item_categories[str(item.id)] = item.categories
        else:
            # Use product_id as key
            item_categories[item.product_id] = item.categories
    metadata["item_categories"] = item_categories
    
    # Build evaluation context
    context = EvaluationContext(
        cart=cart,
        user_id=request.user_id,
        coupons=coupon_configs,
        metadata=metadata
    )
    
    # Evaluate rules
    plan = await engine.evaluate(context)
    
    return _build_discount_response(plan)


@router.post("/evaluate-legacy", response_model=Dict[str, Any])
async def evaluate_rules_legacy(
    cart_id: uuid.UUID,
    user_id: str,
    coupon_codes: List[str],
    engine: RuleEngine = Depends(get_rule_engine)
) -> Dict[str, Any]:
    """Legacy evaluation endpoint for backward compatibility."""
    from src.modules.cart.models import Cart
    
    cart = Cart(
        id=cart_id,
        user_id=user_id,
        items=[]
    )
    
    # Create minimal coupon configs from codes
    coupons = [
        CouponConfig(
            id=uuid.uuid4(),
            name=f"Coupon {code}",
            code=code,
            filters=FilterConfig(),
            eval=EvalConfig(value=Decimal("0")),
            stackable=True,
            priority=100
        )
        for code in coupon_codes
    ]
    
    context = EvaluationContext(
        cart=cart,
        user_id=user_id,
        coupons=coupons
    )
    
    plan = await engine.evaluate(context)
    
    return {
        "applied_coupons": [c.code for c in plan.applied_coupons],
        "rejected_coupons": [c.code for c in plan.rejected_coupons],
        "final_total": plan.final_total,
        "final_discount": plan.final_discount
    }
