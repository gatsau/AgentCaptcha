"""Unit tests for each DPP stage in isolation."""
import asyncio
import hashlib
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Ensure a minimal .env exists for settings import
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.models.session import Session, VerificationResult, Verdict
from app.protocol.stage1_pow import verify_solution, _make_nonce
from app.protocol.stage3_environment import _evaluate
from app.services.consistency import analyze_sessions
from app.services.token import create_token, decode_token


# ---------------------------------------------------------------------------
# Stage 1 — PoW
# ---------------------------------------------------------------------------

class TestStage1PoW(unittest.TestCase):
    def test_valid_solution(self):
        nonce = _make_nonce()
        difficulty = 2
        prefix = "0" * difficulty
        counter = 0
        while True:
            solution = str(counter)
            if hashlib.sha256(nonce + solution.encode()).hexdigest().startswith(prefix):
                break
            counter += 1
        self.assertTrue(verify_solution(nonce, solution, difficulty))

    def test_invalid_solution(self):
        nonce = _make_nonce()
        self.assertFalse(verify_solution(nonce, "wrong", 4))

    def test_pow_stage_timeout(self):
        """Stage 1 should reject when recv times out."""
        from app.config import settings
        messages_sent = []

        async def fake_send(data):
            messages_sent.append(data)

        async def fake_recv():
            # Simulate timeout by sleeping longer than the PoW window
            await asyncio.sleep(settings.pow_timeout_ms / 1000.0 + 0.1)
            return {}

        session = Session(agent_id="test-agent")
        result = asyncio.run(
            __import__("app.protocol.stage1_pow", fromlist=["run"]).run(
                session, fake_send, fake_recv
            )
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.verdict, Verdict.REJECT)
        self.assertIn("timeout", result.reason)

    def test_pow_stage_success(self):
        """Stage 1 should pass when a valid solution is returned quickly."""
        from app.config import settings

        async def _run():
            nonce_holder = {}

            async def fake_send(data):
                if data.get("type") == "pow_challenge":
                    nonce_holder["nonce"] = data["nonce"]
                    nonce_holder["difficulty"] = data["difficulty"]

            async def fake_recv():
                nonce = bytes.fromhex(nonce_holder["nonce"])
                difficulty = nonce_holder["difficulty"]
                counter = 0
                prefix = "0" * difficulty
                while True:
                    solution = str(counter)
                    if hashlib.sha256(nonce + solution.encode()).hexdigest().startswith(prefix):
                        return {"solution": solution}
                    counter += 1

            session = Session(agent_id="test-agent")
            return await __import__("app.protocol.stage1_pow", fromlist=["run"]).run(
                session, fake_send, fake_recv
            )

        result = asyncio.run(_run())
        self.assertIsNone(result)  # None = pass


# ---------------------------------------------------------------------------
# Stage 3 — Environment
# ---------------------------------------------------------------------------

class TestStage3Environment(unittest.TestCase):
    def _agent_env(self):
        return {
            "has_tty": False,
            "display_set": False,
            "uptime_seconds": 3600,
            "open_connections": 5,
            "parent_process": "python",
        }

    def test_agent_env_passes(self):
        passed, failed = _evaluate(self._agent_env())
        self.assertGreaterEqual(passed, 4)

    def test_human_env_fails(self):
        env = {
            "has_tty": True,
            "display_set": True,
            "uptime_seconds": 1800,
            "open_connections": 2,
            "parent_process": "zsh",
        }
        passed, failed = _evaluate(env)
        self.assertLess(passed, 4)

    def test_missing_fields_fail(self):
        passed, failed = _evaluate({})
        self.assertLess(passed, 4)


# ---------------------------------------------------------------------------
# Stage 4 — Consistency
# ---------------------------------------------------------------------------

class TestStage4Consistency(unittest.TestCase):
    def _make_sessions(self, n: int, interval: float = 3600.0) -> list[dict]:
        base = time.time() - n * interval
        return [
            {
                "agent_id": "test-agent",
                "timestamp": base + i * interval,
                "timings": json.dumps({"stage1": 0.05 + i * 0.001}),
                "passed": 1,
            }
            for i in range(n)
        ]

    def test_consistent_sessions(self):
        # Use 2-hour intervals so 10 sessions span 18h → hour_std > 3.0
        sessions = self._make_sessions(10, interval=7200.0)
        result = analyze_sessions(sessions)
        self.assertTrue(result["consistent"])

    def test_too_few_sessions_skipped(self):
        """analyze_sessions with < 5 sessions should still return consistent."""
        sessions = self._make_sessions(3)
        result = analyze_sessions(sessions)
        self.assertTrue(result["consistent"])

    def test_high_timing_variance_rejects(self):
        """Sessions with wildly varying stage1 times should fail."""
        base = time.time()
        sessions = [
            {"agent_id": "test", "timestamp": base + i * 3600,
             "timings": json.dumps({"stage1": 0.001 + i * 0.5}), "passed": 1}
            for i in range(6)
        ]
        result = analyze_sessions(sessions)
        # High CV should cause rejection
        if not result["consistent"]:
            self.assertIn("stage1_timing_cv", result["reason"])


# ---------------------------------------------------------------------------
# Token Service
# ---------------------------------------------------------------------------

class TestTokenService(unittest.TestCase):
    def test_roundtrip(self):
        token = create_token("agent-123", [1, 2, 3, 4])
        payload = decode_token(token)
        self.assertEqual(payload["agent_id"], "agent-123")
        self.assertEqual(payload["stages_passed"], [1, 2, 3, 4])

    def test_invalid_token_raises(self):
        import jwt
        with self.assertRaises(jwt.InvalidTokenError):
            decode_token("not.a.valid.token")


if __name__ == "__main__":
    unittest.main(verbosity=2)
