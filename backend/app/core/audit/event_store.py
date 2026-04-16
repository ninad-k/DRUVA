from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent


class AuditService:
    async def record(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        old_value: dict[str, object] | None,
        new_value: dict[str, object] | None,
        user_id: str | None,
        ip: str | None,
        user_agent: str | None,
        session: AsyncSession,
    ) -> AuditEvent:
        uid = uuid.UUID(user_id) if user_id else None
        event = AuditEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value_jsonb=old_value,
            new_value_jsonb=new_value,
            user_id=uid,
            ip=ip,
            user_agent=user_agent,
        )
        session.add(event)
        await session.flush()
        return event
