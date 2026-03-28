"""Rules module FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.rules.engine import RuleEngine
from src.modules.rules.repository import RuleRepository


async def get_rule_repository(
    db: AsyncSession = Depends(get_db)
) -> RuleRepository:
    """Get RuleRepository instance."""
    return RuleRepository(db)


async def get_rule_engine(
    repo: Annotated[RuleRepository, Depends(get_rule_repository)]
) -> RuleEngine:
    """Get RuleEngine instance."""
    return RuleEngine(repo)
