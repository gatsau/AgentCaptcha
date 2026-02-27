"""
Autonomous agent client: solves PoW, calls Claude for decisions,
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
from anthropic import Anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

WS_URL = os.getenv("WS_URL", "ws://localhost:8000/ws/verify")
AGENT_ID = os.getenv("AGENT_ID", "autonomous-agent-001")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_claude = Anthropic(api_key=ANTHROPIC_API_KEY)


def solve_pow(nonce_hex: str, difficulty: int) -> str:
    """Brute-force SHA-256 PoW: find solution s.t. SHA256(nonce+sol)[:d]=='0'*d."""
    nonce = bytes.fromhex(nonce_hex)
    prefix = "0" * difficulty
    counter = 0
    while True:
        solution = str(counter)
        digest = hashlib.sha256(nonce + solution.encode()).hexdigest()
        if digest.startswith(prefix):
            return solution
        counter += 1


def get_env_metadata() -> dict:
    """Collect real process/environment metadata for Stage 3."""
    proc = psutil.Process()
    try:
        parent_name = psutil.Process(proc.ppid()).name().lower()
    except Exception:
        parent_name = "unknown"

    try:
        connections = len(proc.net_connections())
    except Exception:
        connections = 0

    return {
        "has_tty": sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False,
        "display_set": bool(os.environ.get("DISPLAY")),
        "uptime_seconds": time.time() - psutil.boot_time(),
        "open_connections": connections,
        "parent_process": parent_name,
    }


def answer_decision_challenge(prompt: str, options: list[str]) -> str:
    """Use Claude to answer a semantic decision challenge."""
    options_text = "\n".join(options) if options else "A, B, C, or D"
    response = _claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        system=(
            "You are answering operational decision challenges. "
            "Respond with ONLY the letter of the best option (A, B, C, or D) "
            "and a one-sentence justification, e.g. 'A: Immediate rollback limits blast radius.'"
        ),
        messages=[
            {
                "role": "user",
                "content": f"Question: {prompt}\nOptions:\n{options_text}\nChoose the best option.",
            }
        ],
    )
    return response.content[0].text.strip()


async def run():
    print(f"[agent] Connecting to {WS_URL}?agent_id={AGENT_ID}")
    uri = f"{WS_URL}?agent_id={AGENT_ID}"

    async with websockets.connect(uri) as ws:
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            msg_type = msg.get("type")
            stage = msg.get("stage")

            if msg_type == "pow_challenge":
                print(f"[agent] Stage 1: PoW difficulty={msg['difficulty']}")
                t0 = time.perf_counter()
                solution = solve_pow(msg["nonce"], msg["difficulty"])
                elapsed = time.perf_counter() - t0
                print(f"[agent]   Solved in {elapsed*1000:.1f}ms: {solution}")
                await ws.send(json.dumps({"solution": solution}))

            elif msg_type == "decision_challenge":
                round_num = msg.get("round", "?")
                total = msg.get("total_rounds", "?")
                print(f"[agent] Stage 2: Round {round_num}/{total}")
                answer = answer_decision_challenge(
                    msg.get("prompt", ""), msg.get("options", [])
                )
                print(f"[agent]   Answer: {answer[:60]}")
                await ws.send(json.dumps({"answer": answer}))

            elif msg_type == "env_request":
                print("[agent] Stage 3: Submitting env metadata")
                env = get_env_metadata()
                print(f"[agent]   has_tty={env['has_tty']} display={env['display_set']} parent={env['parent_process']}")
                await ws.send(json.dumps({"env": env}))

            elif msg_type == "result":
                verdict = msg.get("verdict")
                if verdict == "ACCEPT":
                    token = msg.get("token", "")
                    stages = msg.get("stages_passed", [])
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
