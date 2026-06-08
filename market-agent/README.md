# Market Intelligence Agent

A **living competitive-intelligence workspace** for B2B founders and GTM leaders. Give it a company URL and it maps the competitive landscape and surfaces ICP-matched prospects — then it *keeps* that analysis as a workspace that learns from your judgment and tracks how the market moves over time.

Built for the Google Cloud Rapid Agent Hackathon (Arize track). Powered by **Gemini 3** on **Google ADK**, with **Phoenix** observability and a **Phoenix MCP** self-reflection loop.

---

## What it does

- **Grounded competitive analysis.** A profiler agent fetches the company's site and pins down its real identity *before* any analysis runs — so `ptg-usa.com` is correctly read as *Pension Technology Group* (pension software), not guessed from the domain.
- **Competitors + ICP prospects** in one pass: positioning, target segment, pricing, plus real prospect companies with concrete match reasons.
- **A persistent workspace.** Every analysis is saved as a dated snapshot, so a company has a *history* — not a one-shot report.
- **Self-improvement from your judgment.** Keep/Dismiss any competitor or prospect; the agent weights future analyses toward what you keep and away from what you dismiss. Every signal is logged to Phoenix.
- **Change over time.** Re-run and see what moved since the last snapshot — new entrants, dropped players, pricing-tier shifts.
- **Self-reflection.** Ask the agent how it's performing; it queries its *own* telemetry in Phoenix (via the Phoenix MCP server) to answer from real traces and feedback.

## How it works

```
POST /analyze ── ADK SequentialAgent: market_intelligence_agent
                   │
                   ├─ profiler_agent        fetch site → ground company identity   (output: profile)
                   │
                   ├─ ParallelAgent
                   │    ├─ competitive_agent  reads {profile} + your feedback → competitors
                   │    └─ icp_agent          reads {profile} + your feedback → ICP prospects
                   │
                   └─ synthesizer            → structured MarketAnalysis (JSON)
                                              → saved as a snapshot in MongoDB

Feedback loop:  Keep/Dismiss → MongoDB (workspace-scoped) + Phoenix span
                → folded into the next run as session "preferences"

Self-reflection: POST /insights → insights_agent ── Phoenix MCP server (npx) ──→ its own traces/feedback
```

- **Two-layer learning.** *Private* per-workspace personalization (your feedback shapes only your company; never leaves the tenant) + a *shared* improvement signal aggregated in Phoenix — every user makes the base agent smarter without exposing any tenant's strategy.

## Observability & the Arize/Phoenix track

- **Tracing:** `phoenix.otel.register(auto_instrument=True)` with the OpenInference ADK instrumentor sends every agent/LLM/tool span to **Phoenix Cloud**.
- **MCP:** `app/insights.py` attaches the **Phoenix MCP server** (`@arizeai/phoenix-mcp`) to an ADK agent as a toolset, so the agent introspects its own operational data at runtime — the track's MCP-integration requirement. The connection is pre-warmed at boot.
- **Feedback as evals:** Keep/Dismiss is emitted as `user_feedback` spans with `feedback.score` (keep=1 / dismiss=0), the human-feedback layer of the self-improvement loop.

## Tech stack

Python · FastAPI · Google ADK · Gemini 3.5 Flash · MongoDB (workspace persistence) · Arize Phoenix (tracing + MCP) · Next.js 14 + Tailwind (frontend)

## Getting started

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 18+ (for the frontend and the Phoenix MCP server), a MongoDB connection string, a Google API key, and a free [Phoenix Cloud](https://app.phoenix.arize.com) account.

```bash
# 1. Install backend deps
uv sync

# 2. Configure environment
cp .env.example .env   # then fill in the values (see .env.example)

# 3. Run the backend (port 8000). NOTE: no --reload — the reloader fights the MCP subprocess.
.venv/Scripts/uvicorn server:app --port 8000        # Windows
# uv run uvicorn server:app --port 8000             # macOS/Linux

# 4. Run the frontend (port 3000)
cd frontend && npm install && npm run dev
```

Open **http://localhost:3000**, enter a company URL, and Analyze.

> On Windows you can launch the backend, the ADK playground, and the frontend together with `..\start.ps1`.

## API

| Endpoint | Description |
|---|---|
| `POST /analyze` | Run the pipeline for `{company_url}`; saves a snapshot, returns `MarketAnalysis`. |
| `GET /company?url=` | A company's full snapshot history (newest first). |
| `GET /companies` | All companies with at least one analysis. |
| `GET /changes?url=` | Diff of the two most recent snapshots (entrants, exits, pricing shifts). |
| `POST /feedback` | Record a Keep/Dismiss; also logged to Phoenix. |
| `GET /feedback?url=` | All keep/dismiss decisions for a workspace. |
| `POST /insights` | Ask the agent to introspect its own Phoenix telemetry via MCP. |
| `GET /health` | Liveness. |

## Project structure

```
market-agent/
├── app/
│   ├── agent.py          # ADK pipeline (profiler → competitive ∥ icp → synthesizer) + MarketAnalysis schema
│   ├── store.py          # MongoDB persistence, feedback, change-diff
│   ├── observability.py  # Phoenix tracing + feedback spans
│   └── insights.py       # Phoenix MCP self-reflection agent
├── server.py             # FastAPI app (analyze, history, changes, feedback, insights)
├── frontend/             # Next.js workspace UI
└── tests/
```

## License

[AGPL-3.0](../LICENSE). © 2026 Eliannah Linehan.
