"""Rules repository for database operations."""

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundError
from src.modules.rules.models import Rule, Condition, Action


class RuleRepository:
    """Repository for rule database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, rule_id: uuid.UUID | str) -> Optional[Rule]:
        """Get rule by ID with conditions and actions."""
        if isinstance(rule_id, str):
            rule_id = uuid.UUID(rule_id)
        
        result = await self.db.execute(
            select(Rule)
            .options(
                selectinload(Rule.conditions),
                selectinload(Rule.actions)
            )
            .where(Rule.id == rule_id)
        )
        rule = result.scalar_one_or_none()
        
        if rule is None:
            raise NotFoundError("Rule", str(rule_id))
        
        return rule
    
    async def get_active_rules(self) -> List[Rule]:
        """Get all active rules ordered by priority."""
        result = await self.db.execute(
            select(Rule)
            .where(Rule.is_active == True)
            .order_by(Rule.priority.asc())
        )
        return list(result.scalars().all())
    
    async def get_rules_with_conditions_and_actions(self) -> List[Rule]:
        """Get all active rules with eager-loaded conditions and actions."""
        result = await self.db.execute(
            select(Rule)
            .options(
                selectinload(Rule.conditions),
                selectinload(Rule.actions)
            )
            .where(Rule.is_active == True)
            .order_by(Rule.priority.asc())
        )
        return list(result.scalars().all())
    
    async def create(self, rule_data: dict) -> Rule:
        """Create a new rule with conditions and actions."""
        conditions_data = rule_data.pop("conditions", [])
        actions_data = rule_data.pop("actions", [])
        
        rule = Rule(**rule_data)
        
        # Create conditions
        for cond_data in conditions_data:
            condition = Condition(**cond_data)
            rule.conditions.append(condition)
        
        # Create actions
        for action_data in actions_data:
            action = Action(**action_data)
            rule.actions.append(action)
        
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        
        return rule
