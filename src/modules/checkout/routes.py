"""Checkout API routes."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from src.modules.checkout.deps import get_checkout_service
from src.modules.checkout.models import CheckoutStatus, OrderStatus
from src.modules.checkout.service import CheckoutService


router = APIRouter(prefix="/checkout", tags=["checkout"])


# Pydantic Schemas

class CheckoutRequest(BaseModel):
    """Schema for initiating checkout."""
    user_id: str = Field(..., min_length=1)
    coupon_codes: Optional[List[str]] = Field(default=None)


class CheckoutResponse(BaseModel):
    """Schema for checkout response."""
    session_id: uuid.UUID
    order_id: uuid.UUID
    status: CheckoutStatus
    total: Decimal
    discount_total: Decimal
    expires_at: datetime


class CompleteCheckoutRequest(BaseModel):
    """Schema for completing checkout."""
    payment_method: str = Field(..., min_length=1)
    payment_token: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    """Schema for order response."""
    id: uuid.UUID
    cart_id: uuid.UUID
    user_id: str
    status: OrderStatus
    total: Decimal
    discount_total: Decimal


# Routes

@router.post("/{cart_id}", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def init_checkout(
    cart_id: str,
    request: CheckoutRequest,
    service: CheckoutService = Depends(get_checkout_service)
) -> CheckoutResponse:
    """Initialize checkout for a cart."""
    session = await service.init_checkout(
        cart_id=cart_id,
        user_id=request.user_id,
        coupon_codes=request.coupon_codes
    )
    
    return CheckoutResponse(
        session_id=session.id,
        order_id=session.order_id,
        status=session.status,
        total=session.order.total if session.order else Decimal("0.00"),
        discount_total=session.order.discount_total if session.order else Decimal("0.00"),
        expires_at=session.expires_at
    )


@router.post("/{session_id}/complete", response_model=OrderResponse)
async def complete_checkout(
    session_id: str,
    request: CompleteCheckoutRequest,
    service: CheckoutService = Depends(get_checkout_service)
) -> OrderResponse:
    """Complete checkout with payment."""
    payment_result = {
        "success": True,
        "payment_method": request.payment_method,
        "payment_token": request.payment_token
    }
    
    order = await service.complete_checkout(
        session_id=session_id,
        payment_result=payment_result
    )
    
    return OrderResponse(
        id=order.id,
        cart_id=order.cart_id,
        user_id=order.user_id,
        status=order.status,
        total=order.total,
        discount_total=order.discount_total
    )


@router.post("/{session_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_checkout(
    session_id: str,
    service: CheckoutService = Depends(get_checkout_service)
) -> None:
    """Cancel checkout session and release coupon holds."""
    await service.cancel_checkout(session_id)
