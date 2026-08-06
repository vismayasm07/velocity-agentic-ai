import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("configured_url", "expected_url"),
    [
        (
            "postgresql://velocity:secret@internal-host:5432/velocity",
            "postgresql+asyncpg://velocity:secret@internal-host:5432/velocity",
        ),
        (
            "postgres://velocity:secret@internal-host:5432/velocity",
            "postgresql+asyncpg://velocity:secret@internal-host:5432/velocity",
        ),
        (
            "postgresql+asyncpg://velocity:secret@localhost:5432/velocity",
            "postgresql+asyncpg://velocity:secret@localhost:5432/velocity",
        ),
    ],
)
def test_database_url_uses_asyncpg(configured_url: str, expected_url: str) -> None:
    settings = Settings(database_url=configured_url, _env_file=None)

    assert settings.database_url == expected_url