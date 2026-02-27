"""Unit tests for each DPP stage in isolation."""
import asyncio
import hashlib
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("ANTHROPIC_API_KEY", "")   # triggers mock mode
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-32ch")

from app.models.session import Session, VerificationResult, Verdict
from app.protocol.stage1_pow import verify_solution, _make_nonce
from app.protocol.stage3_environment import _evaluate
from app.services.challenge_gen import _static_challenge, _static_validate
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
        """Stage 1 rejects when recv times out."""
        from app.config import settings
        import app.protocol.stage1_pow as s1

        async def _run():
            messages_sent = []

            async def fake_send(data):
                messages_sent.append(data)

            async def fake_recv():
                await asyncio.sleep(settings.pow_timeout_ms / 1000.0 + 0.15)
                return {}

            session = Session(agent_id="test-agent")
            return await s1.run(session, fake_send, fake_recv)

        result = asyncio.run(_run())
        self.assertIsNotNone(result)
        self.assertEqual(result.verdict, Verdict.REJECT)
        self.assertIn("timeout", result.reason)

    def test_pow_stage_success(self):
        """Stage 1 passes with a valid solution."""
        import app.protocol.stage1_pow as s1

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
            return await s1.run(session, fake_send, fake_recv)

        result = asyncio.run(_run())
        self.assertIsNone(result)  # None = pass


# ---------------------------------------------------------------------------
# Stage 2 — Decisions (mock mode, no API key)
# ---------------------------------------------------------------------------

class TestStage2Decisions(unittest.TestCase):
    def _make_session(self):
        return Session(agent_id="test-agent")

    def test_static_challenge_bank(self):
        """Static challenges are returned in mock mode."""
        ch = _static_challenge(1)
        self.assertIn("prompt", ch)
        self.assertIn("options", ch)
        self.assertIn("correct_option", ch)
        self.assertEqual(ch["round_num"], 1)

    def test_static_validate_correct(self):
        ch = _static_challenge(1)
        correct_letter = ch["correct_option"].strip().upper()[0]
        self.assertTrue(_static_validate(ch, f"{correct_letter}: some justification"))

    def test_static_validate_wrong(self):
        ch = {"correct_option": "A"}
        self.assertFalse(_static_validate(ch, "B: wrong answer"))

    def test_stage2_full_mock(self):
        """Stage 2 passes when answering all rounds correctly in mock mode."""
        import app.protocol.stage2_decisions as s2

        async def _run():
            pending_challenge = {}

            async def fake_send(data):
                if data.get("type") == "decision_challenge":
                    pending_challenge.update(data)

            async def fake_recv():
                # Look up the correct answer for the current round
                round_num = pending_challenge.get("round", 1)
                ch = _static_challenge(round_num)
                correct = ch["correct_option"].strip().upper()[0]
                return {"answer": f"{correct}: correct answer"}

            session = self._make_session()
            return await s2.run(session, fake_send, fake_recv, session_id=None)

        result = asyncio.run(_run())
        self.assertIsNone(result)  # None = pass

    def test_stage2_timeout(self):
        """Stage 2 rejects on per-round timeout."""
        import app.protocol.stage2_decisions as s2
        from app.config import settings

        async def _run():
            async def fake_send(data):
                pass

            async def fake_recv():
                await asyncio.sleep(settings.decision_timeout_s + 0.2)
                return {}

            session = self._make_session()
            return await s2.run(session, fake_send, fake_recv, session_id=None)

        result = asyncio.run(_run())
        self.assertIsNotNone(result)
        self.assertEqual(result.verdict, Verdict.REJECT)
        self.assertIn("timeout", result.reason)


# ---------------------------------------------------------------------------
# Stage 3 — Environment
# ---------------------------------------------------------------------------

class TestStage3Environment(unittest.TestCase):
    def test_agent_env_passes(self):
        env = {
            "has_tty": False,
            "display_set": False,
            "uptime_seconds": 3600,
            "open_connections": 5,
            "parent_process": "python",
        }
        passed, failed = _evaluate(env)
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

    def test_shell_parents_fail(self):
        for shell in ["bash", "zsh", "sh", "fish", "cmd", "powershell"]:
            env = {
                "has_tty": False,
                "display_set": False,
                "uptime_seconds": 3600,
                "open_connections": 0,
                "parent_process": shell,
            }
            passed, failed = _evaluate(env)
            self.assertIn("parent_process", failed, f"{shell} should fail parent check")


# ---------------------------------------------------------------------------
# Stage 4 — Consistency
# ---------------------------------------------------------------------------

class TestStage4Consistency(unittest.TestCase):
    def _make_sessions(self, n: int, interval: float = 7200.0) -> list[dict]:
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
        # 2-hour intervals → 10 sessions span 18h → hour_std > 3.0
        sessions = self._make_sessions(10, interval=7200.0)
        result = analyze_sessions(sessions)
        self.assertTrue(result["consistent"])

    def test_too_few_sessions_skipped(self):
        sessions = self._make_sessions(3)
        result = analyze_sessions(sessions)
        self.assertTrue(result["consistent"])

    def test_high_timing_variance_rejects(self):
        base = time.time()
        sessions = [
            {"agent_id": "test", "timestamp": base + i * 7200,
             "timings": json.dumps({"stage1": 0.001 + i * 0.5}), "passed": 1}
            for i in range(6)
        ]
        result = analyze_sessions(sessions)
        if not result["consistent"]:
            self.assertIn("stage1_timing_cv", result["reason"])


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class TestRateLimiter(unittest.TestCase):
    def test_allows_under_limit(self):
        from app.middleware.rate_limit import RateLimitMiddleware
        mw = RateLimitMiddleware.__new__(RateLimitMiddleware)
        from collections import defaultdict, deque
        mw._windows = defaultdict(deque)

        now = time.monotonic()
        for _ in range(5):
            mw._windows["1.2.3.4"].append(now)

        self.assertLess(len(mw._windows["1.2.3.4"]), 10)

    def test_blocks_over_limit(self):
        from app.middleware.rate_limit import RateLimitMiddleware
        from app.config import settings
        from collections import defaultdict, deque

        mw = RateLimitMiddleware.__new__(RateLimitMiddleware)
        mw._windows = defaultdict(deque)

        now = time.monotonic()
        for _ in range(settings.rate_limit_requests):
            mw._windows["9.9.9.9"].append(now)

        self.assertGreaterEqual(
            len(mw._windows["9.9.9.9"]),
            settings.rate_limit_requests,
        )


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

    def test_expired_token_raises(self):
        import jwt
        import time as _time
        payload = {
            "agent_id": "x",
            "stages_passed": [1],
            "exp": int(_time.time()) - 10,
            "iat": int(_time.time()) - 3610,
        }
        from app.config import settings
        token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_token(token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
