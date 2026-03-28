"""Cart facade implementation for cross-module communication."""
import uuid
from typing import Any

from src.modules.cart.service import CartService
from src.modules.cart.models import Cart


class CartFacade:
    """Concrete implementation of cart facade for checkout module integration."""
    
    def __init__(self, cart_service: CartService):
        self._service = cart_service
    
    async def get_cart(self, cart_id: uuid.UUID | str) -> Cart:
        """Get cart by ID."""
        return await self._service.get_by_id(cart_id)


# For backward compatibility with checkout service
ICartService = CartFacade
