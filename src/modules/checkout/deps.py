"""Checkout module FastAPI dependencies."""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db, AsyncSessionLocal
from src.modules.checkout.repository import OrderRepository, CheckoutSessionRepository
from src.modules.checkout.service import CheckoutService, CartFacade, CouponFacade, RulesFacade

# Import real facade implementations
from src.interfaces.facades.cart_facade import CartFacade as RealCartFacade
from src.interfaces.facades.coupon_facade import CouponFacade as RealCouponFacade
from src.interfaces.facades.rules_facade import RulesFacade as RealRulesFacade

# Import underlying services for facade construction
from src.modules.cart.service import CartService as RealCartService
from src.modules.cart.repository import CartRepository
from src.modules.coupon.service import CouponService as RealCouponService
from src.modules.coupon.repository import CouponRepository
from src.modules.rules.engine import RuleEngine
from src.modules.rules.repository import RuleRepository


async def get_order_repository(
    db: AsyncSession = Depends(get_db)
) -> OrderRepository:
    """Get OrderRepository instance."""
    return OrderRepository(db)


async def get_session_repository(
    db: AsyncSession = Depends(get_db)
) -> CheckoutSessionRepository:
    """Get CheckoutSessionRepository instance."""
    return CheckoutSessionRepository(db)


async def get_cart_facade() -> CartFacade:
    """Get CartFacade instance with real implementation."""
    async with AsyncSessionLocal() as db:
        repo = CartRepository(db)
        service = RealCartService(repo)
        return RealCartFacade(service)


async def get_coupon_facade() -> CouponFacade:
    """Get CouponFacade instance with real implementation."""
    async with AsyncSessionLocal() as db:
        repo = CouponRepository(db)
        service = RealCouponService(repo)
        return RealCouponFacade(service)


async def get_rules_facade() -> RulesFacade:
    """Get RulesFacade instance with real implementation."""
    async with AsyncSessionLocal() as db:
        repo = RuleRepository(db)
        engine = RuleEngine(repo)
        return RealRulesFacade(engine)


async def get_checkout_service(
    cart_facade: Annotated[CartFacade, Depends(get_cart_facade)],
    coupon_facade: Annotated[CouponFacade, Depends(get_coupon_facade)],
    rules_facade: Annotated[RulesFacade, Depends(get_rules_facade)],
    order_repo: Annotated[OrderRepository, Depends(get_order_repository)],
    session_repo: Annotated[CheckoutSessionRepository, Depends(get_session_repository)]
) -> CheckoutService:
    """Get CheckoutService instance with all dependencies injected."""
    return CheckoutService(
        cart_facade=cart_facade,
        coupon_facade=coupon_facade,
        rules_facade=rules_facade,
        order_repo=order_repo,
        session_repo=session_repo
    )
