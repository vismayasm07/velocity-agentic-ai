from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

from app.config import get_settings
from app.security import create_access_token, decode_access_token


def test_access_token_round_trip_and_tampering_rejection() -> None:
    user_id = uuid4()
    token, _ = create_access_token(user_id)

    assert decode_access_token(token) == user_id
    replacement = "a" if token[-1] != "a" else "b"
    assert decode_access_token(token[:-1] + replacement) is None


def test_expired_access_token_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(uuid4()), "iat": now - timedelta(minutes=2), "exp": now - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )

    assert decode_access_token(token) is None