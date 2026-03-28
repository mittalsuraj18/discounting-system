"""Cart module FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.cart.repository import CartRepository
from src.modules.cart.service import CartService


async def get_cart_repository(
    db: AsyncSession = Depends(get_db)
) -> CartRepository:
    """Get CartRepository instance."""
    return CartRepository(db)


async def get_cart_service(
    repo: Annotated[CartRepository, Depends(get_cart_repository)]
) -> CartService:
    """Get CartService instance."""
    return CartService(repo)
