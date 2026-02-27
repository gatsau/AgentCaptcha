"""Stage 1: Proof-of-Work gate with 200ms timeout."""
import asyncio
import hashlib
import os
import time

from app.config import settings
from app.models.session import Session, VerificationResult


def _make_nonce() -> bytes:
    return os.urandom(16)


def _target_prefix(difficulty: int) -> str:
    return "0" * difficulty


def verify_solution(nonce: bytes, solution: str, difficulty: int) -> bool:
    digest = hashlib.sha256(nonce + solution.encode()).hexdigest()
    return digest.startswith(_target_prefix(difficulty))


async def run(session: Session, ws_send, ws_recv) -> VerificationResult | None:
    """
    Send nonce to client, await solution within POW_TIMEOUT_MS.
    Returns None on success (updates session), VerificationResult.reject on failure.
    """
    nonce = _make_nonce()
    session.nonce = nonce

    await ws_send({
        "stage": 1,
        "type": "pow_challenge",
        "nonce": nonce.hex(),
        "difficulty": settings.pow_difficulty,
        "timeout_ms": settings.pow_timeout_ms,
    })

    deadline = settings.pow_timeout_ms / 1000.0
    t0 = time.perf_counter()

    try:
        msg = await asyncio.wait_for(ws_recv(), timeout=deadline)
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - t0
        session.timings["stage1"] = elapsed
        return VerificationResult.reject("stage1_timeout")

    elapsed = time.perf_counter() - t0
    session.timings["stage1"] = elapsed

    solution = msg.get("solution", "")
    if not verify_solution(nonce, solution, settings.pow_difficulty):
        return VerificationResult.reject("stage1_invalid_solution")

    session.stage_reached = 1
    return None
