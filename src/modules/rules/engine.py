"""Rule engine for evaluating discount rules based on coupon config schema.

Coupon Config Schema (from Readme):
{
    id: uuid,
    name: human readable name,
    code: unique coupon code like NIKE20,
    filters:{
        include: [],      # filters to apply coupon to (AND filters)
        exclude: [],      # filters to exclude (AND filters)
        min_qty: number,  # optional minimum quantity
        min_value: number # optional minimum cart value
    },
    eval:{
        category: item | total  # level to apply discount
        type: percent | flat | sku | item  # discount type
        value: string           # discount value
        max_value: number       # optional max discount cap
    },
    stackable: true | false,
    priority: number  # lower gets applied first
}

Evaluation Logic:
1. Stackable=True: discounts stack (sum)
2. Stackable=False: compute individually, take max of all
3. Final = max(stacked_discounts, unstacked_1, unstacked_2, ...)
4. ITEM-level discounts are applied first, then TOTAL-level on remaining amount
"""
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.exceptions import RuleError
from src.modules.cart.models import Cart, CartItem
from src.modules.rules.models import Rule, Condition, Action


class EvalCategory(str, Enum):
    """Evaluation category - where to apply discount."""
    ITEM = "item"
    TOTAL = "total"


class EvalType(str, Enum):
    """Evaluation type - how to calculate discount."""
    PERCENT = "percent"
    FLAT = "flat"
    SKU = "sku"    # SKU-specific discount
    ITEM = "item"  # Buy X get Y free style


@dataclass
class FilterConfig:
    """Filter configuration from coupon config."""
    include: List[str] = field(default_factory=list)  # AND filters - must all match
    exclude: List[str] = field(default_factory=list)  # AND filters - must all NOT match
    min_qty: Optional[int] = None
    min_value: Optional[Decimal] = None


@dataclass
class EvalConfig:
    """Evaluation configuration from coupon config."""
    category: EvalCategory = EvalCategory.TOTAL
    type: EvalType = EvalType.PERCENT
    value: Decimal = Decimal("0")
    max_value: Optional[Decimal] = None


@dataclass
class CouponConfig:
    """Complete coupon configuration matching Readme schema."""
    id: uuid.UUID
    name: str
    code: str
    filters: FilterConfig
    eval: EvalConfig
    stackable: bool = True
    priority: int = 100


@dataclass
class ItemDiscount:
    """Discount applied to a specific item."""
    item_id: uuid.UUID
    item_name: str
    original_price: Decimal
    discount_amount: Decimal
    final_price: Decimal
    applied_by: str  # coupon code that applied this discount


@dataclass
class CouponResult:
    """Result of evaluating a single coupon."""
    coupon_id: uuid.UUID
    code: str
    applicable: bool
    reason: str = ""  # why not applicable, or empty if applicable
    
    # Config fields needed for sorting and stacking decisions
    priority: int = 100
    stackable: bool = True
    category: EvalCategory = EvalCategory.TOTAL  # item or total
    
    # For recalculating total-level discounts
    eval_type: Optional[EvalType] = None
    eval_value: Decimal = Decimal("0")
    original_base: Decimal = Decimal("0")
    max_value: Optional[Decimal] = None
    
    # For applicable coupons
    discount_total: Decimal = Decimal("0")
    item_discounts: List[ItemDiscount] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.item_discounts:
            self.item_discounts = []


@dataclass
class DiscountPhaseResult:
    """Result from applying discounts in one phase (item or total)."""
    best_discount: Decimal  # The chosen discount amount
    stacked_discount: Decimal  # Sum of all stackable coupons
    unstacked_alternatives: List[Decimal]  # Individual non-stacked amounts


@dataclass
class DiscountPlan:
    """Final discount calculation result with stacking logic.
    
    Per Readme constraints:
    - stackable=True: discounts sum
    - stackable=False: compute individually, take max
    - Final = max(stacked_discounts, unstacked_1, unstacked_2, ...)
    """
    # Stacked calculation (sum of all stackable coupons)
    stacked_discount: Decimal = Decimal("0")
    stacked_final_total: Decimal = Decimal("0")
    
    # Individual unstacked calculations
    unstacked_alternatives: List[Decimal] = field(default_factory=list)
    
    # Final result (max of stacked and unstacked)
    final_discount: Decimal = Decimal("0")
    final_total: Decimal = Decimal("0")
    
    # Detailed breakdown
    applied_coupons: List[CouponResult] = field(default_factory=list)
    rejected_coupons: List[CouponResult] = field(default_factory=list)
    
    # Item-level discount tracking
    item_discounts: Dict[uuid.UUID, List[ItemDiscount]] = field(default_factory=dict)


@dataclass
class EvaluationContext:
    """Context for rule evaluation."""
    cart: Cart
    user_id: str
    coupons: List[CouponConfig] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def cart_total(self) -> Decimal:
        """Calculate cart total."""
        total = Decimal("0")
        for item in self.cart.items:
            total += item.subtotal
        return total
    
    @property
    def item_count(self) -> int:
        """Count total items in cart."""
        return sum(item.quantity for item in self.cart.items)
    
    def get_item_categories(self, item: CartItem) -> Set[str]:
        """Get categories for a specific item from metadata."""
        # Categories would typically come from product service
        # Format: metadata['item_categories'] = {item_id: [categories]}
        categories = self.metadata.get("item_categories", {})
        return set(categories.get(str(item.id), []))
    
    def get_product_category(self, product_id: str) -> str:
        """Get category for a product from metadata."""
        product_categories = self.metadata.get("product_categories", {})
        return product_categories.get(product_id, "")


class RuleEngine:
    """Engine for evaluating discount rules based on coupon config schema."""
    
    def __init__(self, repository):
        """Initialize with rule repository."""
        self.repository = repository
    
    async def evaluate(self, context: EvaluationContext) -> DiscountPlan:
        """
        Evaluate all coupons against the context with stacking logic.
        
        High-level flow:
        1. Check each coupon for applicability
        2. Apply ITEM-level discounts first (in priority order, respecting stackable)
        3. Apply TOTAL-level discounts on remaining amount (in priority order)
        4. Compute final totals
        """
        plan = DiscountPlan()
        original_total = context.cart_total
        
        # Phase 0: Check all coupons and categorize
        item_coupons, total_coupons = await self._categorize_coupons(context, plan)
        
        if not item_coupons and not total_coupons:
            plan.final_total = original_total
            return plan
        
        # Phase 1: Apply item-level discounts
        item_result = self._apply_discount_phase(item_coupons, original_total)
        
        # Phase 2: Apply total-level discounts on remaining amount
        remaining_after_items = max(Decimal("0"), original_total - item_result.best_discount)
        total_result = self._apply_discount_phase(total_coupons, remaining_after_items)
        
        # Finalize plan with results
        self._finalize_plan(plan, original_total, item_result, total_result)
        
        return plan
    
    async def _categorize_coupons(
        self, 
        context: EvaluationContext, 
        plan: DiscountPlan
    ) -> Tuple[List[CouponResult], List[CouponResult]]:
        """
        Check all coupons and split into item-level and total-level categories.
        
        Returns: (item_coupons, total_coupons) sorted by priority
        """
        # Check each coupon for applicability
        for coupon in context.coupons:
            result = await self._evaluate_coupon(coupon, context)
            if result.applicable:
                plan.applied_coupons.append(result)
            else:
                plan.rejected_coupons.append(result)
        
        # Split by category
        item_coupons = [r for r in plan.applied_coupons if r.category == EvalCategory.ITEM]
        total_coupons = [r for r in plan.applied_coupons if r.category == EvalCategory.TOTAL]
        
        # Sort each group by priority (lower = higher priority)
        item_coupons.sort(key=lambda r: r.priority)
        total_coupons.sort(key=lambda r: r.priority)
        
        # Also sort the plan's applied_coupons by priority for test verification
        plan.applied_coupons.sort(key=lambda r: r.priority)
        
        return item_coupons, total_coupons
    
    def _get_discount_for_base(
        self, 
        coupon: CouponResult, 
        base_amount: Decimal
    ) -> Decimal:
        """Get discount amount for a coupon given a specific base amount.
        
        For ITEM-level coupons, use pre-calculated discount (item prices don't change).
        For TOTAL-level coupons, recalculate based on the provided base_amount.
        """
        if coupon.category == EvalCategory.ITEM:
            # Item-level discounts are pre-calculated based on item prices
            return min(coupon.discount_total, base_amount)
        else:
            # Total-level discounts need recalculation on the new base
            # For now, assume percent discount is proportional to base_amount
            # This handles the common case where discount scales with remaining amount
            if coupon.discount_total > 0:
                # Scale proportionally: new_discount = base_amount * (original_discount / original_base)
                # We don't have original_base stored, so we use a simpler approach:
                # If the coupon was a percent discount, it scales naturally with base_amount
                # For flat discounts, they remain constant (capped at base_amount)
                # For simplicity, we'll recalculate percent-style discounts proportionally
                return min(coupon.discount_total, base_amount)
            return Decimal("0")
    def _apply_discount_phase(
        self, 
        coupons: List[CouponResult], 
        base_amount: Decimal
    ) -> DiscountPhaseResult:
        """
        Apply a set of coupons with stacking logic.
        
        Logic:
        - Stacked: Sum all stackable coupons
        - Non-stacked: Each calculated individually
        - Result: max(stacked, all_non_stacked_individual)
        """
        if not coupons:
            return DiscountPhaseResult(Decimal("0"), Decimal("0"), [])
        
        # Split by stackable
        stackable = [r for r in coupons if r.stackable]
        non_stackable = [r for r in coupons if not r.stackable]
        
        # Calculate stacked discount (sum of all stackable)
        stacked_discount = self._calculate_stacked(stackable, base_amount)
        
        # Calculate each non-stackable individually
        non_stacked_amounts = [
            min(r.discount_total, base_amount) for r in non_stackable
        ]
        
        # Choose best discount
        best_discount = self._choose_best_discount(stacked_discount, non_stacked_amounts)
        
        return DiscountPhaseResult(
            best_discount=best_discount,
            stacked_discount=stacked_discount,
            unstacked_alternatives=non_stacked_amounts
        )
    
    def _calculate_stacked(
        self, 
        coupons: List[CouponResult], 
        base_amount: Decimal
    ) -> Decimal:
        """Calculate cumulative discount from stackable coupons.
        
        All stackable coupons apply to the original base amount (not sequentially).
        This ensures 20% + 10% on $100 = $30, not $28.
        """
        total_discount = Decimal("0")
        
        for coupon in coupons:
            discount = self._recalculate_discount(coupon, base_amount)
            total_discount += discount
        
        # Cap at base_amount to prevent negative totals
        return min(total_discount, base_amount)
    
    def _recalculate_discount(
        self, 
        coupon: CouponResult, 
        base_amount: Decimal
    ) -> Decimal:
        """Recalculate discount for a coupon based on new base_amount.
        
        For TOTAL-level coupons with original_base, use proportional recalculation.
        For ITEM-level or coupons without original_base, use pre-calculated discount.
        """
        if (coupon.category == EvalCategory.TOTAL and 
            coupon.eval_type == EvalType.PERCENT and 
            coupon.original_base > 0):
            # Proportional recalculation: new_discount = old_discount * (new_base / old_base)
            discount = coupon.discount_total * (base_amount / coupon.original_base)
            # Apply max_value cap if present
            if coupon.max_value is not None:
                discount = min(discount, coupon.max_value)
            discount = min(discount, base_amount)
        else:
            # For ITEM-level or when no original_base, use pre-calculated discount
            discount = min(coupon.discount_total, base_amount)
        
        return discount.quantize(Decimal("0.01"))
    
    def _choose_best_discount(
        self, 
        stacked: Decimal, 
        unstacked: List[Decimal]
    ) -> Decimal:
        """Choose the best discount (maximum)."""
        if not unstacked:
            return stacked
        return max([stacked] + unstacked)
    
    def _finalize_plan(
        self,
        plan: DiscountPlan,
        original_total: Decimal,
        item_result: DiscountPhaseResult,
        total_result: DiscountPhaseResult
    ) -> None:
        """Populate the final plan with calculated values."""
        final_discount = item_result.best_discount + total_result.best_discount
        
        plan.final_discount = final_discount
        plan.final_total = max(original_total - final_discount, Decimal("0"))

        plan.stacked_discount = item_result.stacked_discount + total_result.stacked_discount
        plan.stacked_final_total = max(original_total - plan.stacked_discount, Decimal("0"))
        plan.unstacked_alternatives = (
            item_result.unstacked_alternatives + total_result.unstacked_alternatives
        )
    
    async def _evaluate_coupon(
        self, 
        coupon: CouponConfig, 
        context: EvaluationContext
    ) -> CouponResult:
        """Evaluate a single coupon against the context."""
        result = CouponResult(
            coupon_id=coupon.id,
            code=coupon.code,
            applicable=False,
            priority=coupon.priority,
            stackable=coupon.stackable,
            category=coupon.eval.category,
            eval_type=coupon.eval.type,
            eval_value=coupon.eval.value,
            original_base=Decimal("0"),  # Will be set below
            max_value=coupon.eval.max_value,
            discount_total=Decimal("0"),
            item_discounts=[]
        )
        
        # Reject coupons with negative discount values (surcharges not allowed)
        if coupon.eval.value < 0:
            result.reason = "Negative discount value not allowed"
            return result
        
        # Check filters
        filter_check = self._check_filters(coupon.filters, context, coupon)
        if not filter_check[0]:
            result.reason = filter_check[1]
            return result
        
        filtered_items = filter_check[2]  # Items that passed filters
        
        # Calculate discount based on eval config
        if coupon.eval.category == EvalCategory.TOTAL:
            # Total-level discount - calculated on filtered items total only
            filtered_total = sum(item.subtotal for item in filtered_items)
            discount = self._calculate_total_discount(coupon.eval, filtered_total)
            result.discount_total = discount
            result.original_base = filtered_total  # Store for recalculation
            result.applicable = True
            
        elif coupon.eval.category == EvalCategory.ITEM:
            # Item-level discount - only on filtered items
            item_discounts, total_discount = self._calculate_item_discounts(
                coupon, context, filtered_items
            )
            result.item_discounts = item_discounts
            result.discount_total = total_discount
            result.applicable = len(item_discounts) > 0
            if not result.applicable:
                result.reason = "No items match coupon filters"
        
        return result
    
    def _check_filters(
        self, 
        filters: FilterConfig, 
        context: EvaluationContext,
        coupon: CouponConfig
    ) -> Tuple[bool, str, List[CartItem]]:
        """
        Check if context passes all filter conditions.
        
        Logic:
        1. First apply include/exclude filters to get eligible items
        2. Then check min_qty and min_value on the FILTERED items only
        3. Return (passes, reason, filtered_items)
        """
        # Step 1: Filter items by include/exclude
        filtered_items = [
            item for item in context.cart.items
            if self._item_matches_filters(item, filters, context)
        ]
        
        # If no items match after filtering, coupon is not applicable
        if not filtered_items:
            return (False, "No items match coupon filters", [])
        
        # Step 2: Calculate aggregates on FILTERED items only
        filtered_qty = sum(item.quantity for item in filtered_items)
        filtered_value = sum(item.subtotal for item in filtered_items)
        
        # Step 3: Check min_qty on filtered items
        if filters.min_qty is not None:
            if filtered_qty < filters.min_qty:
                return (
                    False, 
                    f"Minimum quantity not met: {filtered_qty} < {filters.min_qty} (after filtering)",
                    filtered_items
                )
        
        # Step 4: Check min_value on filtered items
        if filters.min_value is not None:
            if filtered_value < filters.min_value:
                return (
                    False,
                    f"Minimum value not met: {filtered_value} < {filters.min_value} (after filtering)",
                    filtered_items
                )
        
        return (True, "", filtered_items)
    
    def _matches_filter(self, filter_term: str, context: EvaluationContext) -> bool:
        """Check if cart matches a filter term."""
        # Check in item categories
        for item in context.cart.items:
            categories = context.get_item_categories(item)
            if filter_term in categories:
                return True
            
            # Check product category
            product_category = context.get_product_category(item.product_id)
            if filter_term == product_category:
                return True
            
            # Check if filter is in product_id
            if filter_term in item.product_id:
                return True
        
        # Check in metadata (for payment methods, etc.)
        payment_method = context.metadata.get("payment_method", "")
        if filter_term == payment_method:
            return True
        
        user_segment = context.metadata.get("user_segment", "")
        if filter_term == user_segment:
            return True
        
        return False
    
    def _calculate_total_discount(
        self, 
        eval_config: EvalConfig, 
        base_amount: Decimal
    ) -> Decimal:
        """Calculate discount for total-level evaluation."""
        discount = Decimal("0")
        
        if eval_config.type == EvalType.PERCENT:
            percentage = eval_config.value / Decimal("100")
            discount = base_amount * percentage
        
        elif eval_config.type == EvalType.FLAT:
            discount = eval_config.value
        
        elif eval_config.type == EvalType.ITEM:
            # For total category with item type: value is number of free items
            discount = base_amount * (eval_config.value / Decimal("100"))
        
        # Clamp to minimum 0 (negative discounts/surcharges not allowed)
        discount = max(discount, Decimal("0"))
        
        # Apply max_value cap
        if eval_config.max_value is not None:
            discount = min(discount, eval_config.max_value)
        
        # Ensure discount doesn't exceed base, but only if base is positive
        # For negative base (cart total), no discount can be applied
        if base_amount > 0:
            discount = min(discount, base_amount)
        else:
            discount = Decimal("0")
        
        return discount.quantize(Decimal("0.01"))
    
    def _calculate_item_discounts(
        self, 
        coupon: CouponConfig, 
        context: EvaluationContext,
        filtered_items: List[CartItem]
    ) -> Tuple[List[ItemDiscount], Decimal]:
        """Calculate item-level discounts on filtered items only."""
        item_discounts = []
        total_discount = Decimal("0")
        
        for item in filtered_items:
            item_total = item.subtotal
            discount_amount = self._compute_item_discount(coupon.eval, item)
            
            # Apply max_value cap (per-coupon, distributed across items)
            if coupon.eval.max_value is not None:
                remaining_cap = coupon.eval.max_value - total_discount
                discount_amount = min(discount_amount, remaining_cap)
            
            if discount_amount > 0:
                discount_amount = min(discount_amount, item_total)
                discount_amount = discount_amount.quantize(Decimal("0.01"))
                
                item_discount = ItemDiscount(
                    item_id=item.id,
                    item_name=item.product_id,
                    original_price=item_total,
                    discount_amount=discount_amount,
                    final_price=item_total - discount_amount,
                    applied_by=coupon.code
                )
                item_discounts.append(item_discount)
                total_discount += discount_amount
        
        return (item_discounts, total_discount)
    
    def _compute_item_discount(self, eval_config: EvalConfig, item: CartItem) -> Decimal:
        """Compute discount amount for a single item based on eval config."""
        item_total = item.subtotal
        
        if eval_config.type == EvalType.PERCENT:
            percentage = eval_config.value / Decimal("100")
            return item_total * percentage
        
        elif eval_config.type == EvalType.FLAT:
            return min(eval_config.value, item_total)
        
        elif eval_config.type == EvalType.SKU:
            return min(eval_config.value, item_total)
        
        elif eval_config.type == EvalType.ITEM:
            # Buy X get Y: value is quantity of free items
            if item.quantity > 0:
                free_ratio = min(eval_config.value / Decimal(item.quantity), Decimal("1"))
                discount = item_total * free_ratio
                # Clamp to minimum 0 (negative discounts/surcharges not allowed)
                return max(discount, Decimal("0"))
        
        # Clamp to minimum 0 (safety guard against negative discounts)
        return max(discount, Decimal("0"))
    
    def _item_matches_filters(
        self, 
        item: CartItem, 
        filters: FilterConfig, 
        context: EvaluationContext
    ) -> bool:
        """Check if a specific item matches the coupon filters."""
        # Check exclude first
        if filters.exclude:
            for filter_term in filters.exclude:
                if self._item_matches_filter(item, filter_term, context):
                    return False
        
        # Check include
        if filters.include:
            for filter_term in filters.include:
                if self._item_matches_filter(item, filter_term, context):
                    return True
            return False  # None of the include filters matched
        
        return True  # No include filters means all items match
    
    def _item_matches_filter(
        self, 
        item: CartItem, 
        filter_term: str, 
        context: EvaluationContext
    ) -> bool:
        """Check if a single item matches a filter term."""
        # Check product_id
        if filter_term in item.product_id:
            return True
        
        # Check categories
        categories = context.get_item_categories(item)
        if filter_term in categories:
            return True
        
        # Check product category
        product_category = context.get_product_category(item.product_id)
        if filter_term == product_category:
            return True
        
        # Check metadata filters (payment_method, user_segment, etc.)
        # These are cart-level filters that apply to all items
        payment_method = context.metadata.get("payment_method", "")
        if filter_term == payment_method:
            return True
        
        user_segment = context.metadata.get("user_segment", "")
        if filter_term == user_segment:
            return True
        
        return False