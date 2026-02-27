"""
Simulated human client: sleeps 3s before responding (exceeds PoW timeout).
Should print REJECTED ✗ stage1_timeout.
"""
import asyncio
import json
import os
import sys
import time

import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

WS_URL = os.getenv("WS_URL", "ws://localhost:8000/ws/verify")
HUMAN_ID = os.getenv("HUMAN_ID", "simulated-human-001")


async def run():
    print(f"[human] Connecting to {WS_URL}?agent_id={HUMAN_ID}")
    uri = f"{WS_URL}?agent_id={HUMAN_ID}"

    try:
        async with websockets.connect(uri) as ws:
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "pow_challenge":
                    print(f"[human] Stage 1: Got PoW challenge, thinking for 3 seconds...")
                    await asyncio.sleep(3.0)  # Way too slow — will timeout
                    await ws.send(json.dumps({"solution": "0"}))

                elif msg_type == "result":
                    verdict = msg.get("verdict")
                    if verdict == "ACCEPT":
                        print(f"\n[human] VERIFIED ✓ (unexpected)")
                    else:
                        reason = msg.get("reason", "unknown")
                        print(f"\n[human] REJECTED ✗  reason: {reason}")
                    break

                elif msg_type == "error":
                    print(f"[human] ERROR: {msg.get('message')}")
                    break

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"\n[human] REJECTED ✗  Connection closed by server: {e.reason or 'stage1_timeout'}")


if __name__ == "__main__":
    asyncio.run(run())
