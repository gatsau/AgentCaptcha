"""Stage 4: Cross-session statistical consistency analysis."""
import time

from app.database import fetch_agent_sessions
from app.models.session import Session, VerificationResult
from app.services.consistency import analyze_sessions

_MIN_SESSIONS = 5


async def run(session: Session) -> VerificationResult | None:
    """
    Fetch historical sessions for agent_id, run statistical analysis.
    Skipped if fewer than MIN_SESSIONS exist.
    Returns None on pass/skip, VerificationResult.reject on anomaly.
    """
    t0 = time.perf_counter()
    history = await fetch_agent_sessions(session.agent_id)
    session.timings["stage4_fetch_s"] = time.perf_counter() - t0

    if len(history) < _MIN_SESSIONS:
        session.stage_reached = 4
        return None

    result = analyze_sessions(history)
    session.timings["stage4"] = result

    if not result["consistent"]:
        return VerificationResult.reject(
            f"stage4_inconsistent: {result['reason']}"
        )

    session.stage_reached = 4
    return None
