import os
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config


def main() -> None:
    backend_directory = Path(__file__).resolve().parent
    alembic_config = Config(str(backend_directory / "alembic.ini"))
    command.upgrade(alembic_config, "head")

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()