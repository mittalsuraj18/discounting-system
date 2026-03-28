"""Facade interfaces for cross-module communication.

This module defines concrete implementations that allow the checkout module
to communicate with cart, coupon, and rules modules without direct
dependencies on their internal structures.
"""
from src.interfaces.facades.cart_facade import CartFacade, ICartService
from src.interfaces.facades.coupon_facade import CouponFacade, ICouponService
from src.interfaces.facades.rules_facade import RulesFacade, IRuleService

__all__ = [
    "CartFacade",
    "CouponFacade", 
    "RulesFacade",
    "ICartService",
    "ICouponService",
    "IRuleService",
]
