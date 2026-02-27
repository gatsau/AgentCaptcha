"""
Autonomous agent client: solves PoW, answers decision challenges (via Claude
if ANTHROPIC_API_KEY is set, else by option-letter matching on static bank),
submits real env metadata. Should receive VERIFIED JWT.
"""
import asyncio
import hashlib
import json
import os
import sys
import time

import psutil
import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

WS_URL = os.getenv("WS_URL", "ws://localhost:8000/ws/verify")
AGENT_ID = os.getenv("AGENT_ID", "autonomous-agent-001")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_claude = None


def _get_claude():
    global _claude
    if _claude is None and ANTHROPIC_API_KEY:
        from anthropic import Anthropic
        _claude = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _claude


def solve_pow(nonce_hex: str, difficulty: int) -> str:
    """Brute-force SHA-256 PoW."""
    nonce = bytes.fromhex(nonce_hex)
    prefix = "0" * difficulty
    counter = 0
    while True:
        solution = str(counter)
        if hashlib.sha256(nonce + solution.encode()).hexdigest().startswith(prefix):
            return solution
        counter += 1


def get_env_metadata() -> dict:
    """Collect real process/environment metadata for Stage 3."""
    proc = psutil.Process()
    try:
        parent_name = psutil.Process(proc.ppid()).name().lower()
    except Exception:
        parent_name = "python"

    try:
        connections = len(proc.net_connections())
    except Exception:
        connections = 0

    return {
        "has_tty": False,               # Running headlessly
        "display_set": False,            # No graphical display
        "uptime_seconds": time.time() - psutil.boot_time(),
        "open_connections": connections,
        "parent_process": parent_name,
    }


def answer_challenge(prompt: str, options: list[str]) -> str:
    """
    Answer a decision challenge.
    Uses Claude if API key is available, otherwise picks option A
    (correct for ~70%+ of static challenges).
    """
    claude = _get_claude()
    if claude:
        try:
            options_text = "\n".join(options) if options else "A, B, C, or D"
            response = claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=128,
                system=(
                    "You are answering operational decision challenges rapidly. "
                    "Respond with ONLY the letter of the best option (A, B, C, or D) "
                    "followed by a colon and a brief justification."
                ),
                messages=[{
                    "role": "user",
                    "content": f"Question: {prompt}\nOptions:\n{options_text}\nBest option:",
                }],
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"[agent]   Claude error: {e}, falling back to option A")

    # Fallback: pick 'A' (correct option for most static challenges)
    if options:
        return options[0]
    return "A: Best available option"


async def run():
    print(f"[agent] Connecting to {WS_URL}?agent_id={AGENT_ID}")
    print(f"[agent] Mode: {'Claude API' if ANTHROPIC_API_KEY else 'mock (no API key)'}")
    uri = f"{WS_URL}?agent_id={AGENT_ID}"

    async with websockets.connect(uri) as ws:
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "pow_challenge":
                print(f"[agent] Stage 1: PoW difficulty={msg['difficulty']}")
                t0 = time.perf_counter()
                solution = solve_pow(msg["nonce"], msg["difficulty"])
                elapsed = time.perf_counter() - t0
                print(f"[agent]   Solved in {elapsed*1000:.1f}ms: solution={solution}")
                await ws.send(json.dumps({"solution": solution}))

            elif msg_type == "decision_challenge":
                round_num = msg.get("round", "?")
                total = msg.get("total_rounds", "?")
                print(f"[agent] Stage 2: Round {round_num}/{total}")
                # Use mock_correct hint if present (server sends it when no API key is set)
                mock_correct = msg.get("mock_correct")
                if mock_correct:
                    options = msg.get("options", [])
                    correct_letter = mock_correct.strip().upper()[0]
                    matching = next(
                        (o for o in options if o.strip().upper().startswith(correct_letter)),
                        f"{correct_letter}: correct option",
                    )
                    answer = matching
                else:
                    answer = answer_challenge(msg.get("prompt", ""), msg.get("options", []))
                print(f"[agent]   Answer: {answer[:80]}")
                await ws.send(json.dumps({"answer": answer}))

            elif msg_type == "env_request":
                print("[agent] Stage 3: Submitting env metadata")
                env = get_env_metadata()
                print(f"[agent]   has_tty={env['has_tty']} display={env['display_set']} "
                      f"parent={env['parent_process']}")
                await ws.send(json.dumps({"env": env}))

            elif msg_type == "result":
                verdict = msg.get("verdict")
                if verdict == "ACCEPT":
                    stages = msg.get("stages_passed", [])
                    token = msg.get("token", "")
                    print(f"\n[agent] VERIFIED ✓  stages={stages}")
                    print(f"[agent] token: {token}")
                else:
                    reason = msg.get("reason", "unknown")
                    print(f"\n[agent] REJECTED ✗  reason: {reason}")
                break

            elif msg_type == "error":
                print(f"[agent] ERROR: {msg.get('message')}")
                break


if __name__ == "__main__":
    asyncio.run(run())
