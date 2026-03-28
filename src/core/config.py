"""Core configuration using Pydantic Settings."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/coupon_db",
        alias="DATABASE_URL"
    )
    
    # Application
    app_name: str = Field(default="Coupon Discounting System", alias="APP_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    
    # Security
    secret_key: str = Field(default="dev-secret-key-change-in-production", alias="SECRET_KEY")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
