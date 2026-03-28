"""Test cases for Rule Engine - 23 tests covering all behavioral equivalence classes.

Test Categories:
1. Filter Logic (6 tests) - Item filtering, include/exclude, min_qty, stacked/unstackable puma coupons
2. Eval Types (4 tests) - PERCENT, FLAT, ITEM discount calculations
3. Stacking Logic (4 tests) - Stackable vs non-stackable combinations
4. Two-Phase Evaluation (2 tests) - Item then total phases, negative guard
5. Integration (2 tests) - Readme examples: PUMA BOGO, ICICI percent cap
6. Negative Item Values (4 tests) - Returns/refunds with negative unit prices
7. Negative Discount Value Rejection (1 test) - Surcharges not allowed
"""
import uuid
from decimal import Decimal

import pytest

from src.modules.rules.engine import (
    CouponConfig,
    EvalCategory,
    EvalType,
    FilterConfig,
    EvalConfig,
)


class TestFilterLogic:
    """Tests for filter matching logic - 6 tests."""
    
    @pytest.mark.asyncio
    async def test_include_filter_matches(self, rule_engine, context_factory, coupon_factory):
        """Include filter selects only matching items (puma, not nike)."""
        # Cart: puma shoe @100, nike shoe @150
        ctx = context_factory(
            cart_items=[
                {"product_id": "puma-001", "quantity": 1, "unit_price": 100, "categories": ["puma"]},
                {"product_id": "nike-001", "quantity": 1, "unit_price": 150, "categories": ["nike"]},
            ],
            coupons=[coupon_factory(
                code="PUMA10",
                filters={"include": ["puma"]},
                eval_config={"category": "item", "type": "percent", "value": 10},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # Only puma item should get discount: 10% of 100 = 10
        assert plan.final_discount == Decimal("10.00")
        assert plan.final_total == Decimal("240.00")  # 250 - 10
    
    @pytest.mark.asyncio
    async def test_include_filter_no_match(self, rule_engine, context_factory, coupon_factory):
        """Include filter with no match makes coupon not applicable."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "puma-001", "quantity": 1, "unit_price": 100, "categories": ["puma"]},
            ],
            coupons=[coupon_factory(
                code="ADIDAS20",
                filters={"include": ["adidas"]},  # No adidas in cart
                eval_config={"category": "item", "type": "percent", "value": 20},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # No items match, coupon not applicable
        assert plan.final_discount == Decimal("0")
        assert plan.final_total == Decimal("100.00")
        assert len(plan.rejected_coupons) == 1
        assert "No items match" in plan.rejected_coupons[0].reason
    
    @pytest.mark.asyncio
    async def test_min_qty_on_filtered_items(self, rule_engine, context_factory, coupon_factory):
        """min_qty is checked on FILTERED items only, not whole cart."""
        # Cart: 1 puma, 1 nike - filtered to just puma (qty=1)
        # min_qty=2 requires 2 puma items, but only 1 exists
        ctx = context_factory(
            cart_items=[
                {"product_id": "puma-001", "quantity": 1, "unit_price": 100, "categories": ["puma"]},
                {"product_id": "nike-001", "quantity": 1, "unit_price": 150, "categories": ["nike"]},
            ],
            coupons=[coupon_factory(
                code="PUMA_BULK",
                filters={"include": ["puma"], "min_qty": 2},  # Requires 2 puma items
                eval_config={"category": "item", "type": "percent", "value": 20},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # min_qty not met on filtered (puma) items
        assert plan.final_discount == Decimal("0")
        assert len(plan.rejected_coupons) == 1
        assert "Minimum quantity not met" in plan.rejected_coupons[0].reason
    
    @pytest.mark.asyncio
    async def test_exclude_removes_items(self, rule_engine, context_factory, coupon_factory):
        """Exclude filter removes matching items from discount."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "puma-001", "quantity": 1, "unit_price": 100, "categories": ["puma"]},
                {"product_id": "nike-001", "quantity": 1, "unit_price": 150, "categories": ["nike"]},
            ],
            coupons=[coupon_factory(
                code="ALL_EXCEPT_NIKE",
                filters={"exclude": ["nike"]},  # Exclude nike from discount
                eval_config={"category": "item", "type": "percent", "value": 10},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # Only puma gets discount: 10% of 100 = 10
        assert plan.final_discount == Decimal("10.00")
        assert plan.final_total == Decimal("240.00")  # 250 - 10

    @pytest.mark.asyncio
    async def test_two_stackable_puma_coupons(self, rule_engine, context_factory, coupon_factory):
        """1 puma + 1 adidas item, 2 puma coupons at item level with stackable=True.
        
        Both coupons should apply only to puma item and stack.
        """
        ctx = context_factory(
            cart_items=[
                {"product_id": "puma-001", "quantity": 1, "unit_price": 100, "categories": ["puma"]},
                {"product_id": "adidas-001", "quantity": 1, "unit_price": 80, "categories": ["adidas"]},
            ],
            coupons=[
                coupon_factory(
                    code="PUMA10",
                    filters={"include": ["puma"]},
                    eval_config={"category": "item", "type": "percent", "value": 10},
                    stackable=True,
                ),
                coupon_factory(
                    code="PUMA20",
                    filters={"include": ["puma"]},
                    eval_config={"category": "item", "type": "percent", "value": 20},
                    stackable=True,
                ),
            ],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # Both apply to puma only: 10% + 20% = 30% of 100 = 30 discount
        # Adidas gets no discount
        assert plan.final_discount == Decimal("30.00")
        assert plan.final_total == Decimal("150.00")  # 180 - 30
        assert len(plan.applied_coupons) == 2
    
    @pytest.mark.asyncio
    async def test_two_pumas_unstackable_priority(self, rule_engine, context_factory, coupon_factory):
        """Two unstackable PUMA coupons with different priorities - higher priority wins.

        Priority 10 gives 10% = 10, Priority 20 gives 20% = 20.
        For non-stackable, max discount (20) wins regardless of priority.
        """
        ctx = context_factory(
            cart_items=[
                {"product_id": "puma-001", "quantity": 1, "unit_price": 100, "categories": ["puma"]},
                {"product_id": "adidas-001", "quantity": 1, "unit_price": 80, "categories": ["adidas"]},
            ],
            coupons=[
                coupon_factory(
                    code="PUMA10",
                    filters={"include": ["puma"]},
                    eval_config={"category": "item", "type": "percent", "value": 10},
                    stackable=False,
                    priority=10,
                ),
                coupon_factory(
                    code="PUMA20",
                    filters={"include": ["puma"]},
                    eval_config={"category": "item", "type": "percent", "value": 20},
                    stackable=False,
                    priority=20,
                ),
            ],
        )
        
        plan = await rule_engine.evaluate(ctx)

        # Non-stackable: max discount wins (20% = 20), not priority
        assert plan.final_discount == Decimal("20.00")
        assert plan.final_total == Decimal("160.00")  # 180 - 20
        assert len(plan.applied_coupons) == 2  # Both evaluated, max wins
        # Both coupons applied to same item, higher priority listed first
        assert plan.applied_coupons[0].code == "PUMA10"
        assert plan.applied_coupons[1].code == "PUMA20"


class TestEvalTypes:
    
    @pytest.mark.asyncio
    async def test_percent_discount(self, rule_engine, context_factory, coupon_factory):
        """PERCENT type calculates correctly: 10% of 200 = 20."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 2, "unit_price": 100},
            ],
            coupons=[coupon_factory(
                code="TENPERCENT",
                filters={},
                eval_config={"category": "total", "type": "percent", "value": 10},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        assert plan.final_discount == Decimal("20.00")  # 10% of 200
        assert plan.final_total == Decimal("180.00")
    
    @pytest.mark.asyncio
    async def test_percent_with_max_cap(self, rule_engine, context_factory, coupon_factory):
        """PERCENT with max_value cap: 50% of 200 = 100, but capped at 30."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 2, "unit_price": 100},
            ],
            coupons=[coupon_factory(
                code="BIG_PERCENT",
                filters={},
                eval_config={"category": "total", "type": "percent", "value": 50, "max_value": 30},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        assert plan.final_discount == Decimal("30.00")  # Capped at max_value
        assert plan.final_total == Decimal("170.00")
    
    @pytest.mark.asyncio
    async def test_flat_discount(self, rule_engine, context_factory, coupon_factory):
        """FLAT type gives fixed discount: 50 off 200."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 2, "unit_price": 100},
            ],
            coupons=[coupon_factory(
                code="FLAT50",
                filters={},
                eval_config={"category": "total", "type": "flat", "value": 50},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        assert plan.final_discount == Decimal("50.00")
        assert plan.final_total == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_buy_x_get_y_item_type(self, rule_engine, context_factory, coupon_factory):
        """ITEM type: Buy X get Y free - 4 items @ 100, value=1 -> 25% off = 100 discount."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "shoe-001", "quantity": 4, "unit_price": 100, "categories": ["shoes"]},
            ],
            coupons=[coupon_factory(
                code="BUY3GET1",
                filters={"include": ["shoes"]},
                eval_config={"category": "item", "type": "item", "value": 1},  # 1 free item
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # 1 free out of 4 = 25% discount = 100 off
        assert plan.final_discount == Decimal("100.00")
        assert plan.final_total == Decimal("300.00")


class TestStackingLogic:
    """Tests for discount stacking behavior - 4 tests."""
    
    @pytest.mark.asyncio
    async def test_all_stackable_sums(self, rule_engine, context_factory, coupon_factory):
        """All stackable coupons sum: 100 + 50 = 150 discount."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 1, "unit_price": 500},
            ],
            coupons=[
                coupon_factory(
                    code="STACK100",
                    filters={},
                    eval_config={"category": "total", "type": "flat", "value": 100},
                    stackable=True,
                ),
                coupon_factory(
                    code="STACK50",
                    filters={},
                    eval_config={"category": "total", "type": "flat", "value": 50},
                    stackable=True,
                ),
            ],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # Stackable coupons sum: 100 + 50 = 150
        assert plan.final_discount == Decimal("150.00")
        assert plan.final_total == Decimal("350.00")
    
    @pytest.mark.asyncio
    async def test_non_stackable_takes_max(self, rule_engine, context_factory, coupon_factory):
        """All non-stackable takes max: max(50, 80) = 80 discount."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 1, "unit_price": 500},
            ],
            coupons=[
                coupon_factory(
                    code="NONSTACK50",
                    filters={},
                    eval_config={"category": "total", "type": "flat", "value": 50},
                    stackable=False,
                ),
                coupon_factory(
                    code="NONSTACK80",
                    filters={},
                    eval_config={"category": "total", "type": "flat", "value": 80},
                    stackable=False,
                ),
            ],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # Non-stackable: take max of individual calculations
        assert plan.final_discount == Decimal("80.00")
        assert plan.final_total == Decimal("420.00")
    
    @pytest.mark.asyncio
    async def test_mixed_stackable_logic(self, rule_engine, context_factory, coupon_factory):
        """Mixed: stackable sum vs max of non-stackable. Result = max(stacked, non1, non2)."""
        # stackable=100, non-stackable=[80, 120] -> max(100, 80, 120) = 120
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 1, "unit_price": 500},
            ],
            coupons=[
                coupon_factory(
                    code="STACK100",
                    filters={},
                    eval_config={"category": "total", "type": "flat", "value": 100},
                    stackable=True,
                ),
                coupon_factory(
                    code="NONSTACK80",
                    filters={},
                    eval_config={"category": "total", "type": "flat", "value": 80},
                    stackable=False,
                ),
                coupon_factory(
                    code="NONSTACK120",
                    filters={},
                    eval_config={"category": "total", "type": "flat", "value": 120},
                    stackable=False,
                ),
            ],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # max(100, 80, 120) = 120
        assert plan.final_discount == Decimal("120.00")
        assert plan.final_total == Decimal("380.00")
    
    @pytest.mark.asyncio
    async def test_priority_sorting(self, rule_engine, context_factory, coupon_factory):
        """Lower priority number = higher priority, applied first."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 1, "unit_price": 100},
            ],
            coupons=[
                coupon_factory(
                    code="LOW_PRIORITY",
                    filters={},
                    eval_config={"category": "total", "type": "percent", "value": 10},
                    priority=100,  # Lower priority (higher number = later)
                ),
                coupon_factory(
                    code="HIGH_PRIORITY",
                    filters={},
                    eval_config={"category": "total", "type": "percent", "value": 20},
                    priority=10,  # Higher priority (lower number = first)
                ),
            ],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # Both applied (stackable), order matters for stacking but result is sum
        # 20% + 10% = 30% of 100 = 30
        assert plan.final_discount == Decimal("30.00")
        assert plan.final_total == Decimal("70.00")
        
        # Verify priority sorting: HIGH_PRIORITY (10) should be first
        assert plan.applied_coupons[0].priority == 10
        assert plan.applied_coupons[1].priority == 100


class TestTwoPhaseEvaluation:
    """Tests for two-phase evaluation (item then total) - 2 tests."""
    
    @pytest.mark.asyncio
    async def test_item_then_total_phases(self, rule_engine, context_factory, coupon_factory):
        """ITEM 10% then TOTAL 5% on $100: 10 off, then 5% of 90 = 4.50, final 85.50."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "shoe-001", "quantity": 1, "unit_price": 100, "categories": ["shoes"]},
            ],
            coupons=[
                coupon_factory(
                    code="ITEM10",
                    filters={"include": ["shoes"]},
                    eval_config={"category": "item", "type": "percent", "value": 10},
                ),
                coupon_factory(
                    code="TOTAL5",
                    filters={},
                    eval_config={"category": "total", "type": "percent", "value": 5},
                ),
            ],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # Item phase: 10% of 100 = 10
        # Total phase: 5% of remaining (90) = 4.50
        # Total discount: 14.50
        assert plan.final_discount == Decimal("14.50")
        assert plan.final_total == Decimal("85.50")
    
    @pytest.mark.asyncio
    async def test_discount_never_negative(self, rule_engine, context_factory, coupon_factory):
        """100% discount on $50 cart - should never go negative (max 50 discount)."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 1, "unit_price": 50},
            ],
            coupons=[coupon_factory(
                code="FULL100",
                filters={},
                eval_config={"category": "total", "type": "percent", "value": 100},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # Discount capped at cart total, final never negative
        assert plan.final_discount == Decimal("50.00")
        assert plan.final_total == Decimal("0.00")


class TestIntegration:
    """Integration tests from Readme examples - 2 tests."""
    
    @pytest.mark.asyncio
    async def test_puma_bogo_readme(self, rule_engine, context_factory, coupon_factory):
        """Readme example: 2 puma shoes @100, min_qty=1, type=ITEM, value=1 -> 100 discount (50% off)."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "puma-shoe-001", "quantity": 2, "unit_price": 100, "categories": ["puma", "shoes"]},
            ],
            coupons=[coupon_factory(
                code="PUMA_BOGO",
                filters={"include": ["puma"], "min_qty": 1},
                eval_config={"category": "item", "type": "item", "value": 1},  # 1 free
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # 1 free out of 2 = 50% = 100 discount
        assert plan.final_discount == Decimal("100.00")
        assert plan.final_total == Decimal("100.00")
    
    @pytest.mark.asyncio
    async def test_icici_percent_cap_readme(self, rule_engine, context_factory, coupon_factory):
        """Readme example: Total=3000, payment=icici, 10% max 500 -> 300 discount."""
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 3, "unit_price": 1000},
            ],
            metadata={"payment_method": "icici"},
            coupons=[coupon_factory(
                code="ICICI10",
                filters={"include": ["icici"]},  # Matches payment_method in metadata
                eval_config={"category": "total", "type": "percent", "value": 10, "max_value": 500},
            )],
        )
        
        plan = await rule_engine.evaluate(ctx)
        
        # 10% of 3000 = 300, which is < 500 cap, so 300 discount
        assert plan.final_discount == Decimal("300.00")
        assert plan.final_total == Decimal("2700.00")



class TestNegativeItemValues:
    """Tests for items with negative values (returns/refunds) - 4 tests."""
    @pytest.mark.asyncio
    async def test_negative_unit_price_item(self, rule_engine, context_factory, coupon_factory):
        """Negative unit price item reduces cart total - discount applies to net total."""
        # Cart: 1 positive item @ 200, 1 negative item @ -50 (return)
        # Cart total = 150
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 1, "unit_price": 200, "categories": ["electronics"]},
                {"product_id": "return-001", "quantity": 1, "unit_price": -50, "categories": ["returns"]},
            ],
            coupons=[coupon_factory(
                code="TENPERCENT",
                filters={},
                eval_config={"category": "total", "type": "percent", "value": 10},
            )],
        )

        plan = await rule_engine.evaluate(ctx)

        # 10% of 150 = 15 discount, final = 135
        assert plan.final_discount == Decimal("15.00")
        assert plan.final_total == Decimal("135.00")

    @pytest.mark.asyncio
    async def test_negative_item_with_include_filter(self, rule_engine, context_factory, coupon_factory):
        """Include filter on category excludes negative items in different category."""
        # Cart: 2 puma @ 100 each, 1 return @ -30 in different category
        # Filter on puma, discount applies to puma items only
        ctx = context_factory(
            cart_items=[
                {"product_id": "puma-001", "quantity": 2, "unit_price": 100, "categories": ["puma"]},
                {"product_id": "return-shoe", "quantity": 1, "unit_price": -30, "categories": ["returns"]},
            ],
            coupons=[coupon_factory(
                code="PUMA20",
                filters={"include": ["puma"]},
                eval_config={"category": "item", "type": "percent", "value": 20},
            )],
        )

        plan = await rule_engine.evaluate(ctx)

        # 20% of 200 (puma items only) = 40 discount
        # Cart total = 200 - 30 = 170, final after discount = 130
        assert plan.final_discount == Decimal("40.00")
        assert plan.final_total == Decimal("130.00")  # 170 - 40

    @pytest.mark.asyncio
    async def test_mixed_positive_negative_with_flat_discount(self, rule_engine, context_factory, coupon_factory):
        """Flat discount capped at net cart total when negative items present."""
        # Cart: 100 + 50 - 30 = 120 net total
        # Flat discount 150 should be capped at 120 (net cart total)
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 1, "unit_price": 100},
                {"product_id": "item-002", "quantity": 1, "unit_price": 50},
                {"product_id": "return-001", "quantity": 1, "unit_price": -30},
            ],
            coupons=[coupon_factory(
                code="FLAT150",
                filters={},
                eval_config={"category": "total", "type": "flat", "value": 150},
            )],
        )

        plan = await rule_engine.evaluate(ctx)

        # Discount capped at cart total (120), not 150
        assert plan.final_discount == Decimal("120.00")
        assert plan.final_total == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_negative_item_makes_cart_negative_with_discount(self, rule_engine, context_factory, coupon_factory):
        """If negative items exceed positive, cart is negative - no discount possible."""
        # Cart: 100 positive, -150 return = -50 net cart total
        # No discount should be applied, final remains -50
        ctx = context_factory(
            cart_items=[
                {"product_id": "item-001", "quantity": 1, "unit_price": 100},
                {"product_id": "return-001", "quantity": 1, "unit_price": -150},
            ],
            coupons=[coupon_factory(
                code="TENPERCENT",
                filters={},
                eval_config={"category": "total", "type": "percent", "value": 10},
            )],
        )

        plan = await rule_engine.evaluate(ctx)

        # Cart total is -50, no discount can be applied
        # Discount is 0 (can't discount negative cart), final remains -50
        assert plan.final_discount == Decimal("0.00")
        assert plan.final_total == Decimal("-50.00")


    @pytest.mark.asyncio
    async def test_negative_discount_value_rejected(self, rule_engine, context_factory, coupon_factory):
        """Negative discount value should cause coupon to be rejected."""
        ctx = context_factory(
            cart_items=[{"product_id": "item-001", "quantity": 1, "unit_price": 100}],
            coupons=[coupon_factory(
                code="INVALIDNEG",
                filters={},
                eval_config={"category": "total", "type": "percent", "value": -10},
            )],
        )
        plan = await rule_engine.evaluate(ctx)
        
        # Coupon with negative value should be rejected
        assert plan.final_discount == Decimal("0.00")
        assert plan.final_total == Decimal("100.00")  # No change
        assert len(plan.rejected_coupons) == 1
        assert "Negative discount value not allowed" in plan.rejected_coupons[0].reason
