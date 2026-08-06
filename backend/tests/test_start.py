from pathlib import Path
from unittest.mock import Mock

import start


def test_start_applies_migrations_before_serving(monkeypatch) -> None:
    calls: list[str] = []
    upgrade = Mock(side_effect=lambda *_: calls.append("migrate"))
    run = Mock(side_effect=lambda *_args, **_kwargs: calls.append("serve"))
    monkeypatch.setattr(start.command, "upgrade", upgrade)
    monkeypatch.setattr(start.uvicorn, "run", run)
    monkeypatch.setenv("PORT", "9876")

    start.main()

    alembic_config = upgrade.call_args.args[0]
    assert Path(alembic_config.config_file_name).name == "alembic.ini"
    upgrade.assert_called_once_with(alembic_config, "head")
    run.assert_called_once_with(
        "app.main:app", host="0.0.0.0", port=9876
    )
    assert calls == ["migrate", "serve"]