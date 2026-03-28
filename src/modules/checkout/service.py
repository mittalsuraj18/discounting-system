"""Checkout service for business logic."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Protocol

from src.core.exceptions import NotFoundError, CheckoutError, ValidationError
from src.modules.checkout.models import Order, CheckoutSession, OrderStatus, CheckoutStatus
from src.modules.checkout.repository import OrderRepository, CheckoutSessionRepository


# Protocol definitions for facades - allows dependency injection without circular imports
class CartFacade(Protocol):
    """Protocol for cart facade operations."""
    async def get_cart(self, cart_id: uuid.UUID | str) -> Any: ...


class CouponFacade(Protocol):
    """Protocol for coupon facade operations."""
    async def validate(self, code: str, cart: Any) -> Any: ...
    async def hold(self, coupon_ids: List[uuid.UUID], order_id: uuid.UUID) -> bool: ...
    async def release(self, coupon_ids: List[uuid.UUID], order_id: uuid.UUID) -> bool: ...


class RulesFacade(Protocol):
    """Protocol for rules engine facade operations."""
    async def evaluate(self, cart: Any, coupons: List[Any]) -> Any: ...


class DiscountPlan:
    """Result from rules evaluation."""
    def __init__(self, total: Decimal, discount_total: Decimal, applied_coupons: List[Any]):
        self.total = total
        self.discount_total = discount_total
        self.applied_coupons = applied_coupons


class CheckoutService:
    """Service for checkout business logic."""
    
    def __init__(
        self,
        cart_facade: CartFacade,
        coupon_facade: CouponFacade,
        rules_facade: RulesFacade,
        order_repo: OrderRepository,
        session_repo: CheckoutSessionRepository
    ):
        self.cart_facade = cart_facade
        self.coupon_facade = coupon_facade
        self.rules_facade = rules_facade
        self.order_repo = order_repo
        self.session_repo = session_repo
    
    async def init_checkout(
        self,
        cart_id: uuid.UUID | str,
        user_id: str,
        coupon_codes: Optional[List[str]] = None
    ) -> CheckoutSession:
        """Initialize checkout: validate cart, evaluate discounts, hold coupons, create order."""
        # 1. Get cart via cart_facade
        try:
            cart = await self.cart_facade.get_cart(cart_id)
        except Exception as e:
            raise CheckoutError(f"Failed to retrieve cart: {str(e)}")
        
        # 2. Validate coupons via coupon_facade
        valid_coupons = []
        if coupon_codes:
            for code in coupon_codes:
                try:
                    coupon = await self.coupon_facade.validate(code, cart)
                    if coupon:
                        valid_coupons.append(coupon)
                except Exception:
                    # Skip invalid coupons, continue with others
                    pass
        
        # 3. Call rules_facade.evaluate with cart + valid coupons
        try:
            discount_plan = await self.rules_facade.evaluate(cart, valid_coupons)
        except Exception as e:
            raise CheckoutError(f"Failed to evaluate discounts: {str(e)}")
        
        # Ensure discount_plan has required attributes
        if not hasattr(discount_plan, 'total'):
            raise CheckoutError("Invalid discount plan: missing total")
        
        # 4. Create order with discount_plan.total
        order = await self.order_repo.create(
            cart_id=cart.id if hasattr(cart, 'id') else uuid.UUID(str(cart_id)),
            user_id=user_id,
            total=discount_plan.total,
            discount_total=getattr(discount_plan, 'discount_total', Decimal("0.00"))
        )
        
        # 5. Hold coupons if any
        held_coupon_ids = []
        if valid_coupons and hasattr(discount_plan, 'applied_coupons') and discount_plan.applied_coupons:
            applied_coupons = discount_plan.applied_coupons
            coupon_ids = [
                c.id for c in applied_coupons 
                if hasattr(c, 'id')
            ]
            if coupon_ids:
                try:
                    await self.coupon_facade.hold(coupon_ids, order.id)
                    held_coupon_ids = coupon_ids
                except Exception as e:
                    # Continue even if hold fails - order is created
                    pass
        
        # 6. Create checkout_session
        session = await self.session_repo.create(order.id)
        
        # Update session with held coupons
        held_coupons_data = [
            {"coupon_id": str(c.id), "code": getattr(c, 'code', None)}
            for c in valid_coupons if hasattr(c, 'id')
        ]
        await self.session_repo.update_held_coupons(session.id, held_coupons_data)
        
        # Update status based on whether coupons were applied
        if held_coupon_ids:
            await self.session_repo.update_status(session.id, CheckoutStatus.COUPON_APPLIED)
        
        return session
    
    async def complete_checkout(
        self,
        session_id: uuid.UUID | str,
        payment_result: Optional[Dict[str, Any]] = None
    ) -> Order:
        """Complete checkout: process payment, confirm order."""
        session = await self.session_repo.get_by_id(session_id)
        
        # Check if session is expired
        if session.expires_at < datetime.utcnow():
            raise CheckoutError("Checkout session has expired")
        
        # Check if session can be completed
        if session.status == CheckoutStatus.COMPLETED:
            raise CheckoutError("Checkout already completed")
        
        if session.status == CheckoutStatus.FAILED:
            raise CheckoutError("Checkout session has failed")
        
        # Update session status to payment pending if not already
        if session.status == CheckoutStatus.INITIATED:
            await self.session_repo.update_status(session.id, CheckoutStatus.PAYMENT_PENDING)
        
        # Simulate payment processing (payment_result would contain actual payment info)
        payment_success = True
        if payment_result:
            payment_success = payment_result.get("success", True)
        
        if not payment_success:
            await self.session_repo.update_status(session.id, CheckoutStatus.FAILED)
            raise CheckoutError("Payment failed")
        
        # Update order status to paid
        order = await self.order_repo.update_status(session.order_id, OrderStatus.PAID)
        
        # Update session status to completed
        await self.session_repo.update_status(session.id, CheckoutStatus.COMPLETED)
        
        return order
    
    async def cancel_checkout(self, session_id: uuid.UUID | str) -> None:
        """Cancel checkout: release coupon holds, cancel order."""
        session = await self.session_repo.get_by_id(session_id)
        
        # Check if already completed
        if session.status == CheckoutStatus.COMPLETED:
            raise CheckoutError("Cannot cancel completed checkout")
        
        # Release held coupons
        if session.held_coupons:
            coupon_ids = [
                uuid.UUID(c.get("coupon_id")) 
                for c in session.held_coupons 
                if c.get("coupon_id")
            ]
            if coupon_ids:
                try:
                    await self.coupon_facade.release(coupon_ids, session.order_id)
                except Exception:
                    # Continue even if release fails
                    pass
        
        # Update order status to cancelled
        await self.order_repo.update_status(session.order_id, OrderStatus.CANCELLED)
        
        # Update session status
        await self.session_repo.update_status(session.id, CheckoutStatus.FAILED)
