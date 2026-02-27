"""Stage 3: Environment attestation — process tree, TTY, display checks."""
import asyncio
import time

from app.models.session import Session, VerificationResult

# Required keys and their agent-like expected values
_CHECKS = {
    "has_tty": False,          # Agents don't have a TTY
    "display_set": False,      # Agents don't have DISPLAY
    "uptime_seconds": None,    # Checked separately (> 0)
    "open_connections": None,  # Checked separately (>= 0)
    "parent_process": None,    # Checked separately (not bash/zsh/sh)
}

_HUMAN_SHELLS = {"bash", "zsh", "sh", "fish", "cmd", "powershell", "pwsh"}


def _evaluate(env: dict) -> tuple[int, list[str]]:
    """Return (checks_passed, failed_check_names)."""
    passed = 0
    failed = []

    # Check 1: no TTY
    if env.get("has_tty") is False:
        passed += 1
    else:
        failed.append("has_tty")

    # Check 2: no DISPLAY
    if not env.get("display_set", True):
        passed += 1
    else:
        failed.append("display_set")

    # Check 3: uptime > 0
    uptime = env.get("uptime_seconds", -1)
    if isinstance(uptime, (int, float)) and uptime >= 0:
        passed += 1
    else:
        failed.append("uptime_seconds")

    # Check 4: open_connections is a non-negative integer
    conns = env.get("open_connections", -1)
    if isinstance(conns, int) and conns >= 0:
        passed += 1
    else:
        failed.append("open_connections")

    # Check 5: parent process is not an interactive shell
    parent = env.get("parent_process", "").lower()
    if parent and parent not in _HUMAN_SHELLS:
        passed += 1
    else:
        failed.append("parent_process")

    return passed, failed


async def run(session: Session, ws_send, ws_recv) -> VerificationResult | None:
    """
    Request env dict from client, verify 4/5 conditions pass.
    Returns None on success, VerificationResult.reject on failure.
    """
    await ws_send({
        "stage": 3,
        "type": "env_request",
        "required_fields": list(_CHECKS.keys()),
    })

    t0 = time.perf_counter()
    try:
        msg = await asyncio.wait_for(ws_recv(), timeout=5.0)
    except asyncio.TimeoutError:
        return VerificationResult.reject("stage3_timeout")

    elapsed = time.perf_counter() - t0
    session.timings["stage3"] = elapsed

    env = msg.get("env", {})
    session.env_data = env

    passed_count, failed = _evaluate(env)

    if passed_count < 4:
        return VerificationResult.reject(
            f"stage3_env_checks_failed={','.join(failed)}"
        )

    session.stage_reached = 3
    return None
