# AgentCaptcha — Project Context

> Keep this file updated as work progresses. It's the single source of truth for picking up where we left off.

---

## What This Is

A working Python implementation of the **Decision-Proof Protocol (DPP)** from Max's research paper. It's a server that verifies whether a connecting client is an autonomous AI agent or a human-operated system, issuing a JWT on success.

Think of it as a reverse CAPTCHA — it lets agents in and keeps humans out.

---

## Tech Stack

| Layer | Library |
|-------|---------|
| Server | FastAPI + uvicorn |
| Transport | WebSocket (`/ws/verify`) + REST |
| Database | aiosqlite (SQLite) |
| LLM | Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) |
| Auth | PyJWT (HS256) |
| Stats | numpy |
| Process inspection | psutil |
| Config | pydantic-settings + `.env` |
| Rate limiting | In-memory sliding-window middleware |
| Containers | Docker + docker-compose |

Python version: **3.11** (`/opt/homebrew/bin/python3.11`)

---

## Repository

```
https://github.com/gatsau/AgentCaptcha.git
/Users/maxkennedy/AgentCaptcha/
```

---

## Verification Stages

| # | Name | How it works | Pass condition |
|---|------|-------------|----------------|
| 1 | **Proof of Work** | SHA-256(nonce + solution) must start with `0000` | Solved within 200ms |
| 2 | **Semantic Decisions** | 10 rounds of Claude-generated (or static) operational scenarios | ≥70% correct + timing CV < 0.8 |
| 3 | **Environment Attestation** | Client submits env dict: TTY, DISPLAY, parent process, uptime, connections | 4/5 checks pass |
| 4 | **Cross-Session Consistency** | numpy analysis of historical timing patterns across sessions | Skipped if < 5 prior sessions |

---

## How to Run

```bash
cd /Users/maxkennedy/AgentCaptcha

# First time only
cp .env.example .env
# Optionally add ANTHROPIC_API_KEY for live Claude challenges (works without it too)

# Start server
/opt/homebrew/bin/python3.11 run.py

# Autonomous agent (should print VERIFIED ✓)
/opt/homebrew/bin/python3.11 demo/agent_client.py

# Simulated human (should print REJECTED ✗ stage1_timeout)
/opt/homebrew/bin/python3.11 demo/human_client.py

# Inspect a JWT
curl "localhost:8000/verify?token=<token>"

# Session history
curl "localhost:8000/sessions/<agent_id>"
curl "localhost:8000/sessions/<agent_id>/history/<session_id>"

# Unit tests
/opt/homebrew/bin/python3.11 tests/test_stages.py

# Docker
docker compose up --build
```

---

## Current State — COMPLETE ✓

- [x] Full 4-stage protocol implemented
- [x] WebSocket handler + REST endpoints
- [x] aiosqlite persistence (sessions + challenge history per round)
- [x] JWT issuance on success + `/verify?token=` inspection endpoint
- [x] `/sessions/{agent_id}` and `/sessions/{agent_id}/history/{session_id}` endpoints
- [x] Static challenge bank (12 ops scenarios) — works without ANTHROPIC_API_KEY
- [x] Claude API integration — auto-enabled when ANTHROPIC_API_KEY is set
- [x] `mock_correct` hint in mock mode so demo agent always answers correctly
- [x] Sliding-window rate limiter (10 req/60s per IP, configurable)
- [x] Autonomous agent demo client — VERIFIED ✓ all 4 stages
- [x] Simulated human demo client — REJECTED ✗ stage1_timeout
- [x] Unit tests — 21/21 passing
- [x] Dockerfile + docker-compose.yml
- [x] Pushed to GitHub

---

## API Quick Reference

| Method | Path | Description |
|--------|------|-------------|
| WS | `/ws/verify?agent_id=<id>` | Run full DPP verification |
| GET | `/status` | Health check + mock_mode flag |
| GET | `/verify?token=<jwt>` | Decode and inspect a JWT |
| GET | `/sessions/<agent_id>` | All sessions for an agent |
| GET | `/sessions/<agent_id>/history/<session_id>` | Per-round challenge history |

---

## Known Notes

- `python3` on this machine is 3.8 (system). Always use `/opt/homebrew/bin/python3.11`
- Without `ANTHROPIC_API_KEY`, server runs in mock mode (logged as WARNING on startup)
- In mock mode, `mock_correct` field is included in Stage 2 WS messages so demo clients respond correctly
- Stage 4 consistency analysis only activates after ≥5 sessions for an agent_id
- JWT `exp` is 3600s from issue time; use `/verify?token=` to inspect

---

## Possible Future Enhancements

- Record-and-replay: store full WS session traces for forensic review
- Admin dashboard (FastAPI + Jinja2) showing live session stats
- Pluggable challenge providers (add custom scenario banks)
- Redis-backed rate limiting for multi-process deployments
- Webhook: POST to configurable URL on ACCEPT/REJECT
