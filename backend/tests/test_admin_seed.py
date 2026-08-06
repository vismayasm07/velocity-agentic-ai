import asyncio

from sqlalchemy import func, select

from app.config import get_settings
from app.database import async_session_factory, engine
from app.models import User
from app.security import verify_password
from app.seed import seed_default_admin


async def verify_admin_seed() -> None:
    settings = get_settings()
    email = str(settings.admin_email).lower()

    await asyncio.gather(seed_default_admin(), seed_default_admin())

    async with async_session_factory() as session:
        admin = await session.scalar(select(User).where(User.email == email))
        admin_count = await session.scalar(
            select(func.count()).select_from(User).where(User.email == email)
        )

    assert admin is not None
    assert admin_count == 1
    assert admin.is_admin
    assert admin.is_active
    assert admin.created_at is not None
    assert admin.updated_at is not None
    assert admin.password_hash != settings.admin_password
    assert verify_password(admin.password_hash, settings.admin_password)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(verify_admin_seed())
    print("Default admin seed verified.")