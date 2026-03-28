"""Coupon API routes."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from src.core.exceptions import CouponError, NotFoundError, ValidationError
from src.modules.coupon.deps import get_coupon_service
from src.modules.coupon.service import CouponService, ValidationResult

router = APIRouter(prefix="/coupon", tags=["coupon"])


# Pydantic Schemas

class CouponCreateRequest(BaseModel):
    """Schema for creating a coupon."""
    code: str = Field(..., min_length=1, max_length=255)
    rule_id: uuid.UUID
    max_uses: int = Field(..., gt=0)
    valid_from: datetime
    valid_until: datetime
    is_active: bool = True
    
    @field_validator("valid_until")
    @classmethod
    def validate_date_range(cls, v: datetime, info) -> datetime:
        values = info.data
        if "valid_from" in values and values["valid_from"] >= v:
            raise ValueError("valid_until must be after valid_from")
        return v


class CouponResponse(BaseModel):
    """Schema for coupon response."""
    id: uuid.UUID
    code: str
    rule_id: uuid.UUID
    max_uses: int
    current_uses: int
    valid_from: datetime
    valid_until: datetime
    is_active: bool


class ValidationResponse(BaseModel):
    """Schema for coupon validation response."""
    valid: bool
    code: Optional[str]
    discount_preview: Decimal
    message: str


# Helper function to build response

def _build_coupon_response(coupon) -> CouponResponse:
    """Build CouponResponse from Coupon model."""
    return CouponResponse(
        id=coupon.id,
        code=coupon.code,
        rule_id=coupon.rule_id,
        max_uses=coupon.max_uses,
        current_uses=coupon.current_uses,
        valid_from=coupon.valid_from,
        valid_until=coupon.valid_until,
        is_active=coupon.is_active
    )


def _build_validation_response(result: ValidationResult, code: str) -> ValidationResponse:
    """Build ValidationResponse from ValidationResult."""
    return ValidationResponse(
        valid=result.valid,
        code=code if result.coupon else None,
        discount_preview=result.discount_value,
        message=result.message
    )


# Routes

@router.get("/{code}", response_model=ValidationResponse)
async def validate_coupon(
    code: str,
    user_id: str = Query(..., description="User ID for validation context"),
    cart_id: Optional[str] = Query(None, description="Cart ID for validation context"),
    service: CouponService = Depends(get_coupon_service)
) -> ValidationResponse:
    """Validate a coupon code."""
    cart_uuid = uuid.UUID(cart_id) if cart_id else uuid.uuid4()
    
    result = await service.validate(code, user_id, cart_uuid)
    
    if not result.valid and result.coupon is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message
        )
    
    return _build_validation_response(result, code)


@router.post("/", response_model=CouponResponse, status_code=status.HTTP_201_CREATED)
async def create_coupon(
    request: CouponCreateRequest,
    service: CouponService = Depends(get_coupon_service)
) -> CouponResponse:
    """Create a new coupon (admin only)."""
    coupon_data = {
        "code": request.code,
        "rule_id": request.rule_id,
        "max_uses": request.max_uses,
        "valid_from": request.valid_from,
        "valid_until": request.valid_until,
        "is_active": request.is_active
    }
    
    try:
        coupon = await service.create_coupon(coupon_data)
        return _build_coupon_response(coupon)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.message
        )
    except CouponError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
