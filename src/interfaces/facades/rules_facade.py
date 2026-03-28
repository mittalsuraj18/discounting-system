"""Rules facade implementation for cross-module communication."""
from typing import Any, List

from src.modules.rules.engine import (
    RuleEngine, 
    EvaluationContext, 
    DiscountPlan, 
    CouponConfig,
    FilterConfig,
    EvalConfig,
    EvalCategory,
    EvalType,
)
from src.modules.rules.repository import RuleRepository
from src.modules.rules.models import Rule, Action, Condition, ActionType


class RulesFacade:
    """Concrete implementation of rules facade for checkout module integration."""
    
    def __init__(self, rule_engine: RuleEngine):
        self._engine = rule_engine
    
    async def evaluate(self, cart: Any, coupons: List[Any]) -> DiscountPlan:
        """Evaluate rules for cart and coupons.
        
        Args:
            cart: Cart object with items
            coupons: List of Coupon objects (from DB) or CouponConfig objects
        
        Returns:
            DiscountPlan with applied discounts per Readme stacking rules
        """
        # Build evaluation context
        user_id = getattr(cart, 'user_id', 'anonymous')
        
        # Convert database coupons to CouponConfig if needed
        coupon_configs = []
        for c in coupons:
            if c is not None:
                if isinstance(c, CouponConfig):
                    coupon_configs.append(c)
                else:
                    # Convert database Coupon model to CouponConfig
                    config = self._convert_coupon_to_config(c)
                    coupon_configs.append(config)
        
        context = EvaluationContext(
            cart=cart,
            user_id=user_id,
            coupons=coupon_configs
        )
        
        # Evaluate and return
        plan = await self._engine.evaluate(context)
        return plan
    
    def _convert_coupon_to_config(self, coupon: Any) -> CouponConfig:
        """Convert a database Coupon model to CouponConfig.
        
        This extracts rule data from the coupon's associated rule.
        """
        import uuid as uuid_module
        from decimal import Decimal
        
        # Get rule from coupon if available
        rule = getattr(coupon, 'rule', None)
        
        if rule:
            # Extract filters from conditions
            include = []
            exclude = []
            min_qty = None
            min_value = None
            
            for condition in getattr(rule, 'conditions', []):
                if condition.type.value == 'category':
                    try:
                        import json
                        val = json.loads(condition.value)
                        if isinstance(val, list):
                            include.extend(val)
                        else:
                            include.append(str(val))
                    except:
                        include.append(condition.value)
                elif condition.type.value == 'item_count' and condition.operator.value == 'gte':
                    try:
                        min_qty = int(condition.value)
                    except:
                        pass
                elif condition.type.value == 'cart_total' and condition.operator.value == 'gte':
                    try:
                        min_value = Decimal(str(condition.value))
                    except:
                        pass
            
            # Extract eval config from actions
            eval_category = EvalCategory.TOTAL
            eval_type = EvalType.PERCENT
            eval_value = Decimal("0")
            max_value = None
            
            for action in getattr(rule, 'actions', []):
                if action.target.value == 'item':
                    eval_category = EvalCategory.ITEM
                
                if action.type == ActionType.percent:
                    eval_type = EvalType.PERCENT
                elif action.type == ActionType.flat:
                    eval_type = EvalType.FLAT
                elif action.type == ActionType.item:
                    eval_type = EvalType.ITEM
                
                eval_value = Decimal(str(action.value))
                if action.max_discount:
                    max_value = action.max_discount
            
            return CouponConfig(
                id=getattr(coupon, 'id', uuid_module.uuid4()),
                name=getattr(rule, 'name', getattr(coupon, 'code', 'Unknown')),
                code=getattr(coupon, 'code', 'UNKNOWN'),
                filters=FilterConfig(
                    include=include,
                    exclude=exclude,
                    min_qty=min_qty,
                    min_value=min_value
                ),
                eval=EvalConfig(
                    category=eval_category,
                    type=eval_type,
                    value=eval_value,
                    max_value=max_value
                ),
                stackable=True,  # Default, could come from rule metadata
                priority=getattr(rule, 'priority', 100)
            )
        
        # Fallback: create minimal config from coupon only
        return CouponConfig(
            id=getattr(coupon, 'id', uuid_module.uuid4()),
            name=getattr(coupon, 'code', 'Unknown'),
            code=getattr(coupon, 'code', 'UNKNOWN'),
            filters=FilterConfig(),
            eval=EvalConfig(),
            stackable=True,
            priority=100
        )


# For backward compatibility
IRuleService = RulesFacade
