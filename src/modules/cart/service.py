"""Cart service for business logic."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from src.modules.cart.models import Cart, CartItem, CartStatus
from src.modules.cart.repository import CartRepository


class CartService:
    """Service for cart business logic."""
    
    def __init__(self, repository: CartRepository):
        self.repository = repository
    
    async def get_by_id(self, cart_id: uuid.UUID | str) -> Cart:
        """Get cart by ID."""
        return await self.repository.get_by_id(cart_id)
    
    async def create(
        self,
        user_id: str,
        items_data: List[dict]
    ) -> Cart:
        """Create a new cart with validated items."""
        # Validate items
        items = []
        for item_data in items_data:
            self._validate_item(item_data)
            item = CartItem(
                id=uuid.uuid4(),
                product_id=item_data["product_id"],
                quantity=item_data["quantity"],
                unit_price=Decimal(str(item_data["unit_price"]))
            )
            items.append(item)
        
        return await self.repository.create(user_id, items)
    
    async def delete(self, cart_id: uuid.UUID | str) -> None:
        """Delete cart by ID."""
        await self.repository.delete(cart_id)
    
    def _validate_item(self, item_data: dict) -> None:
        """Validate cart item data."""
        if item_data.get("quantity", 0) <= 0:
            raise ValueError("Quantity must be greater than 0")
        
        if not item_data.get("product_id"):
            raise ValueError("Product ID is required")
        
        if item_data.get("unit_price") is None:
            raise ValueError("Unit price is required")
    
    def calculate_total(self, cart: Cart) -> Decimal:
        """Calculate total amount for cart."""
        total = Decimal("0")
        for item in cart.items:
            total += item.subtotal
        return total
