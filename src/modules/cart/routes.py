"""Cart API routes."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator

from src.modules.cart.deps import get_cart_service
from src.modules.cart.models import CartStatus
from src.modules.cart.service import CartService

router = APIRouter(prefix="/cart", tags=["cart"])


# Pydantic Schemas

class CartItemCreate(BaseModel):
    """Schema for creating a cart item."""
    product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    unit_price: Decimal = Field(..., gt=0, decimal_places=2)


class CartCreateRequest(BaseModel):
    """Schema for creating a cart."""
    user_id: str = Field(..., min_length=1)
    items: List[CartItemCreate]


class CartItemResponse(BaseModel):
    """Schema for cart item response."""
    id: uuid.UUID
    product_id: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class CartResponse(BaseModel):
    """Schema for cart response."""
    id: uuid.UUID
    user_id: str
    status: CartStatus
    items: List[CartItemResponse]
    total: Decimal
    expires_at: datetime
    created_at: datetime


# Helper function to build response

def _build_cart_response(cart, service: CartService) -> CartResponse:
    """Build CartResponse from Cart model."""
    items = [
        CartItemResponse(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal
        )
        for item in cart.items
    ]
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        status=cart.status,
        items=items,
        total=service.calculate_total(cart),
        expires_at=cart.expires_at,
        created_at=cart.created_at
    )


# Routes

@router.post("/", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
async def create_cart(
    request: CartCreateRequest,
    service: CartService = Depends(get_cart_service)
) -> CartResponse:
    """Create a new cart with items."""
    items_data = [
        {
            "product_id": item.product_id,
            "quantity": item.quantity,
            "unit_price": item.unit_price
        }
        for item in request.items
    ]
    
    cart = await service.create(request.user_id, items_data)
    return _build_cart_response(cart, service)


@router.delete("/{cart_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cart(
    cart_id: str,
    service: CartService = Depends(get_cart_service)
) -> None:
    """Delete cart by ID."""
    await service.delete(cart_id)


@router.get("/{cart_id}", response_model=CartResponse)
async def get_cart(
    cart_id: str,
    service: CartService = Depends(get_cart_service)
) -> CartResponse:
    """Get cart by ID."""
    cart = await service.get_by_id(cart_id)
    return _build_cart_response(cart, service)
