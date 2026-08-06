from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.database import async_session_factory
from app.models import Deal, MonitoringSettings, User
from app.security import hash_password


async def seed_default_admin() -> None:
    settings = get_settings()
    email = settings.admin_email.lower()

    async with async_session_factory() as session:
        await session.execute(
            insert(User)
            .values(
                email=email,
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
                is_active=True,
            )
            .on_conflict_do_nothing(index_elements=[User.email])
        )
        await session.commit()


async def seed_default_deals() -> None:
    now = datetime.now(UTC)
    deals = [
        {
            "id": UUID("10000000-0000-4000-8000-000000000001"),
            "name": "Northstar Analytics Expansion",
            "value": Decimal("86000.00"),
            "stage": "Proposal",
            "owner_name": "Maya Chen",
            "stage_entered_at": now - timedelta(days=3),
            "last_activity_at": now - timedelta(hours=5),
            "next_follow_up_at": now + timedelta(days=2),
            "status": "active",
            "created_at": now - timedelta(days=24),
        },
        {
            "id": UUID("10000000-0000-4000-8000-000000000002"),
            "name": "Acme Systems Renewal",
            "value": Decimal("42000.00"),
            "stage": "Discovery",
            "owner_name": "Liam Brooks",
            "stage_entered_at": now - timedelta(days=16),
            "last_activity_at": now - timedelta(days=12),
            "next_follow_up_at": None,
            "status": "inactive",
            "created_at": now - timedelta(days=45),
        },
        {
            "id": UUID("10000000-0000-4000-8000-000000000003"),
            "name": "Vertex Health Platform",
            "value": Decimal("119500.00"),
            "stage": "Negotiation",
            "owner_name": "Ava Patel",
            "stage_entered_at": now - timedelta(days=7),
            "last_activity_at": now - timedelta(days=4),
            "next_follow_up_at": now - timedelta(days=2),
            "status": "active",
            "created_at": now - timedelta(days=38),
        },
        {
            "id": UUID("10000000-0000-4000-8000-000000000004"),
            "name": "Meridian Global Transformation",
            "value": Decimal("475000.00"),
            "stage": "Proposal",
            "owner_name": "Noah Garcia",
            "stage_entered_at": now - timedelta(days=5),
            "last_activity_at": now - timedelta(days=1),
            "next_follow_up_at": now + timedelta(days=1),
            "status": "active",
            "created_at": now - timedelta(days=31),
        },
        {
            "id": UUID("10000000-0000-4000-8000-000000000005"),
            "name": "Brightline Commerce Pilot",
            "value": Decimal("28000.00"),
            "stage": "Qualified",
            "owner_name": "Maya Chen",
            "stage_entered_at": now - timedelta(hours=6),
            "last_activity_at": now - timedelta(hours=2),
            "next_follow_up_at": now + timedelta(days=3),
            "status": "active",
            "created_at": now - timedelta(hours=8),
        },
    ]

    async with async_session_factory() as session:
        await session.execute(
            insert(Deal).values(deals).on_conflict_do_nothing(index_elements=[Deal.id])
        )
        await session.commit()


async def seed_monitoring_settings() -> None:
    settings = get_settings()
    async with async_session_factory() as session:
        existing = await session.scalar(select(MonitoringSettings.id).limit(1))
        if existing is not None:
            return
        admin_id = await session.scalar(
            select(User.id).where(User.email == settings.admin_email.lower())
        )
        if admin_id is None:
            raise RuntimeError("Default admin must exist before monitoring settings are seeded")
        session.add(
            MonitoringSettings(
                monitoring_enabled=settings.proactive_monitoring_enabled,
                scan_interval_seconds=settings.proactive_monitoring_interval_seconds,
                stage_sla_hours=168,
                inactivity_threshold_hours=120,
                overdue_follow_up_enabled=True,
                owner_overload_enabled=True,
                owner_max_active_deals=18,
                owner_max_high_risk_deals=5,
                owner_max_overdue_follow_ups=5,
                automatic_rca_enabled=False,
                automatic_rca_min_risk_score=80,
                outcome_verification_enabled=True,
                outcome_check_delay_minutes=60,
                maximum_outcome_checks=3,
                resolution_risk_threshold=20,
                updated_by=admin_id,
            )
        )
        await session.commit()