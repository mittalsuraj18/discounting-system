"""Main FastAPI application factory."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.database import init_db
from src.modules.cart.routes import router as cart_router
from src.modules.coupon.routes import router as coupon_router
from src.modules.checkout.routes import router as checkout_router
from src.modules.rules.routes import router as rules_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup: Initialize database tables (dev mode)
    # In production, use Alembic migrations instead
    if settings.debug:
        await init_db()
    
    yield
    
    # Shutdown: Cleanup if needed
    pass


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="Hybrid Modular Coupon/Discount System with Rule Engine",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include module routers
    # Cart module: POST /cart/, DELETE /cart/{cart_id}, GET /cart/{cart_id}
    app.include_router(
        cart_router,
        prefix="/cart",
        tags=["Cart"]
    )
    
    # Coupon module: GET /coupon/{code}, POST /coupon
    app.include_router(
        coupon_router,
        prefix="/coupon",
        tags=["Coupon"]
    )
    
    # Checkout module: POST /checkout/{cart_id}
    app.include_router(
        checkout_router,
        prefix="/checkout",
        tags=["Checkout"]
    )
    
    # Rules module: POST /rule/evaluate
    app.include_router(
        rules_router,
        prefix="/rule",
        tags=["Rules"]
    )
    
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}
    
    return app


# Global app instance for uvicorn
app = create_application()
