# AgentCaptcha — Decision-Proof Protocol (DPP)

A working implementation of the Decision-Proof Protocol from Max Kennedy's research paper. Verifies whether a connecting client is an **autonomous AI agent** or a **human-operated system**, issuing a signed JWT on success.

## Architecture

Four verification stages run sequentially over a WebSocket connection:

| Stage | Name | Test | Timeout |
|-------|------|------|---------|
| 1 | **Proof of Work** | SHA-256 hash with 4-zero prefix | 200ms |
| 2 | **Semantic Decisions** | 10 rounds of LLM-generated operational challenges | 1.5s/round |
| 3 | **Environment Attestation** | Process tree, TTY, DISPLAY, uptime, connections | 5s |
| 4 | **Cross-Session Consistency** | numpy analysis of historical timing patterns | N/A |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY and JWT_SECRET

# Terminal 1: start server
python run.py

# Terminal 2: autonomous agent — should print "VERIFIED ✓ token: eyJ..."
python demo/agent_client.py

# Terminal 3: human simulation — should print "REJECTED ✗ stage1_timeout"
python demo/human_client.py

# Inspect a token
curl localhost:8000/verify/<token>

# Run unit tests
python tests/test_stages.py
```

## WebSocket Protocol

Connect to `ws://localhost:8000/ws/verify?agent_id=<your-id>`

The server drives the conversation. Each message is a JSON object with a `type` field:

### Server → Client

```json
{"stage": 1, "type": "pow_challenge", "nonce": "<hex>", "difficulty": 4, "timeout_ms": 200}
{"stage": 2, "type": "decision_challenge", "round": 1, "total_rounds": 10, "prompt": "...", "options": [...], "prev_answer_hash": "..."}
{"stage": 3, "type": "env_request", "required_fields": ["has_tty", "display_set", ...]}
{"type": "result", "verdict": "ACCEPT", "token": "<jwt>", "stages_passed": [1,2,3,4]}
{"type": "result", "verdict": "REJECT", "reason": "stage1_timeout"}
```

### Client → Server

```json
{"solution": "<string>"}                          // Stage 1
{"answer": "<option letter + justification>"}     // Stage 2
{"env": {"has_tty": false, "display_set": false, "uptime_seconds": 3600, "open_connections": 5, "parent_process": "python"}}  // Stage 3
```

## REST API

- `GET /status` — health check
- `GET /verify/{token}` — decode and inspect a verification JWT

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | required | Claude API key |
| `JWT_SECRET` | `change-me` | HMAC secret for JWT signing |
| `DATABASE_URL` | `./agentcaptcha.db` | SQLite path |
| `POW_DIFFICULTY` | `4` | Leading zeros required |
| `POW_TIMEOUT_MS` | `200` | PoW solve deadline |
| `DECISION_ROUNDS` | `10` | Number of challenge rounds |
| `DECISION_TIMEOUT_S` | `1.5` | Per-round deadline |

## Stage Details

### Stage 1 — Proof of Work
Find string `s` such that `SHA256(nonce + s)` has `POW_DIFFICULTY` leading hex zeros.
Agents solve this in microseconds; humans cannot solve it within 200ms.

### Stage 2 — Semantic Decisions
Claude Haiku generates market/debug/ops scenarios. Each challenge's hash is chained
into the next prompt. After all rounds: if timing CV > 0.4, the response pattern
is human-like (irregular pauses) and the session is rejected.

### Stage 3 — Environment Attestation
Checks 5 signals; requires 4/5 to pass as agent-like:
- `has_tty: false` — no interactive terminal
- `display_set: false` — no graphical display
- `uptime_seconds >= 0` — valid system uptime
- `open_connections >= 0` — valid connection count
- `parent_process` not in `{bash, zsh, sh, fish, cmd, powershell}`

### Stage 4 — Cross-Session Consistency
After 5+ sessions for an agent_id, numpy analysis checks:
- PoW solve time coefficient of variation (< 0.6 expected for consistent compute)
- Hour-of-day distribution (agents operate 24/7; humans cluster in working hours)

## Project Structure

```
app/
├── main.py              # FastAPI app
├── config.py            # Pydantic settings
├── database.py          # aiosqlite: sessions + history tables
├── protocol/
│   ├── stage1_pow.py    # PoW gate
│   ├── stage2_decisions.py  # Semantic challenges
│   ├── stage3_environment.py  # Env attestation
│   ├── stage4_consistency.py  # Statistical analysis
│   └── verifier.py      # Orchestrator
├── models/
│   ├── session.py       # Session, VerificationResult
│   └── challenge.py     # Challenge, ChallengeResponse, Stage
├── api/
│   ├── websocket.py     # WS handler
│   └── routes.py        # REST endpoints
└── services/
    ├── challenge_gen.py # Claude API: generate + validate
    ├── token.py         # PyJWT
    └── consistency.py   # numpy stats
demo/
├── agent_client.py      # Autonomous agent
└── human_client.py      # Simulated human
tests/
└── test_stages.py       # Unit tests
```
