"""JWT encode/decode using PyJWT."""
import time
import jwt

from app.config import settings

_ALGORITHM = "HS256"
_EXPIRY_S = 3600


def create_token(agent_id: str, stages_passed: list[int]) -> str:
    now = int(time.time())
    payload = {
        "agent_id": agent_id,
        "verified_at": now,
        "expires_in": _EXPIRY_S,
        "stages_passed": stages_passed,
        "exp": now + _EXPIRY_S,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.exceptions on invalid/expired."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
