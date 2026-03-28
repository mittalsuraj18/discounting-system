"""Internal EventBus for module communication."""
from typing import Callable, Any, Awaitable
from collections import defaultdict
import asyncio


EventHandler = Callable[[Any], Awaitable[None]]


class EventBus:
    """Simple async event bus for internal module communication."""
    
    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
    
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type."""
        self._handlers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
    
    async def publish(self, event_type: str, payload: Any) -> None:
        """Publish an event to all subscribed handlers."""
        handlers = self._handlers.get(event_type, [])
        if handlers:
            await asyncio.gather(
                *[handler(payload) for handler in handlers],
                return_exceptions=True
            )


# Global event bus instance
event_bus = EventBus()
