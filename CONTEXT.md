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
| 2 | **Semantic Decisions** | 10 rounds of Claude-generated operational scenarios (market, debug, etc.) | ≥70% correct + timing CV < 0.4 |
| 3 | **Environment Attestation** | Client submits env dict: TTY, DISPLAY, parent process, uptime, connections | 4/5 checks pass |
| 4 | **Cross-Session Consistency** | numpy analysis of historical timing patterns across sessions | Skipped if < 5 prior sessions |

---

## How to Run

```bash
cd /Users/maxkennedy/AgentCaptcha

# First time only: copy and fill in secrets
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and JWT_SECRET

# Start server
/opt/homebrew/bin/python3.11 run.py

# Autonomous agent client (should print VERIFIED ✓)
/opt/homebrew/bin/python3.11 demo/agent_client.py

# Simulated human client (should print REJECTED ✗ stage1_timeout)
/opt/homebrew/bin/python3.11 demo/human_client.py

# Inspect a token
curl localhost:8000/verify/<token>

# Unit tests
/opt/homebrew/bin/python3.11 tests/test_stages.py
```

---

## Current State

- [x] Full 4-stage protocol implemented
- [x] WebSocket handler + REST endpoints
- [x] aiosqlite persistence (sessions + challenge history)
- [x] JWT issuance on success
- [x] Autonomous agent demo client
- [x] Simulated human demo client
- [x] Unit tests — 12/12 passing
- [x] Pushed to GitHub

---

## Next Steps

- [ ] **Run end-to-end demo** — start server, run both demo clients, verify output matches expected
- [ ] **Stage 2 accuracy tuning** — test whether Haiku-generated challenges are challenging enough; may need to adjust prompt or bump to Sonnet
- [ ] **Stage 4 real data** — run agent_client.py 5+ times and verify Stage 4 activates and passes
- [ ] **Rate limiting** — add per-IP/agent_id rate limiting to prevent brute-force
- [ ] **Async DB writes** — challenge_history table is created but not written to yet (stage2_decisions should persist per-round results)
- [ ] **Docker / deployment** — Dockerfile + docker-compose for easy hosting
- [ ] **README gif/demo** — record the terminal demo described in the plan

---

## Known Issues / Notes

- `python3` on this machine is 3.8 (system). Always use `/opt/homebrew/bin/python3.11`
- JWT test emits `InsecureKeyLengthWarning` — harmless in tests, use a 32+ byte secret in production
- Stage 4's hour-distribution check only kicks in at ≥10 sessions; normal in early use
- `.env` is gitignored — never committed
