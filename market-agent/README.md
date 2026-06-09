# Market Intelligence Agent

A **living competitive-intelligence workspace** for B2B founders and GTM leaders. Give it a company URL and it maps the competitive landscape and surfaces ICP-matched prospects — then it *keeps* that analysis as a workspace that learns from your judgment and tracks how the market moves over time.

Built for the Google Cloud Rapid Agent Hackathon (Arize track). Powered by **Gemini 3** on **Google ADK**, with **Phoenix** observability and a **Phoenix MCP** self-reflection loop.

---

## What it does

- **Grounded analysis.** A profiler agent fetches the company's site and pins down its real identity *before* any analysis runs — identified from what the homepage actually says, not guessed from the domain or an ambiguous abbreviation.
- **Competitors + ICP prospects** in one pass: positioning, target segment, pricing, and real prospect companies with concrete match reasons.
- **An accumulating workspace, not a one-shot report.** Re-scans *merge* into a persistent, deduped set. You **Keep** (pin to a shortlist) or **Dismiss** (hide) any item; anything you don't touch stays a candidate — nothing silently vanishes.
- **It learns your judgment.** Your Keep/Dismiss shapes future scans — and that learning signal is read back **from Arize Phoenix**, where it's also evaluated and measured.
- **Change over time.** A re-scan surfaces genuine new entrants since last time (not LLM re-roll churn).
- **Self-reflection.** Ask the agent how it's doing; it queries its *own* Phoenix telemetry via the Phoenix MCP server.

## Architecture

![Architecture — ADK agent pipeline, the curated workspace, and Arize Phoenix as the evaluation & improvement engine](docs/architecture.png)

### Agent map — the ADK pipeline

```
POST /analyze (company URL)
        │
        ▼
  market_intelligence_agent                 ← ADK SequentialAgent · Gemini 3.5 Flash
        │
  1 ─▶ profiler_agent       fetch homepage → grounded company profile
        │                   tool: fetch_company_website            (output_key: profile)
        │
  2 ─▶ parallel_research                                            ← ADK ParallelAgent
        ├─ competitive_agent   reads {profile} + {preferences}  → competitors
        └─ icp_agent           reads {profile} + {preferences}  → ICP prospects
        │
  3 ─▶ synthesizer          reads {profile}{competitive}{icp}
        │                   → MarketAnalysis  (structured JSON via output_schema)
        ▼
  MERGE into the curated workspace
  (MongoDB `items`, status: candidate | kept | dismissed, deduped by normalized name)
```

### Self-improvement loop — where Arize Phoenix is the engine

```
        ┌──────────────────────────── re-scan (periodic) ───────────────────────────┐
        ▼                                                                            │
  ① RUN ──── ADK pipeline ─────────────────────────────▶ traced to Phoenix          │
                                                          (OpenInference spans)      │
  ② EVALUATE                                                                         │
       • groundedness  (LLM-as-judge: is it the right company?)                      │
       • usefulness    (keep-rate)                  ───────────▶ evals in Phoenix     │
  ③ CURATE  founder Keep / Dismiss                                                   │
       • Mongo item status   → the Shortlist the user sees (fast, transactional)     │
       • Phoenix annotation  → tenant-tagged human feedback                          │
  ④ LEARN   next scan's preferences are READ BACK FROM PHOENIX ─────────────────────┘
            (the tenant's graded keep/dismiss history; Mongo fallback for freshness)
  ⑤ MEASURE keep-rate & groundedness trend over time, in Phoenix
```

**The division of labor:** **MongoDB** is the product's fast memory (the curated list the user sees). **Arize Phoenix** is the agent's *evaluation & improvement engine* — it traces every run, scores it on two axes (machine groundedness + human usefulness), is the source the next scan **learns from** (Tier 2 reads keep/dismiss back from Phoenix), and is what the `/insights` agent **introspects via MCP**. Runs are meant to be time-separated ("re-scans"), so Phoenix's batch-export lag is a non-issue; Mongo covers freshness for back-to-back use.

**Tenancy & privacy.** Everything is tagged with `tenant.id` so Layer-1 personalization stays private to a workspace, while Layer-2 (aggregate eval metrics / datasets) can improve the base agent across tenants without exposing any one tenant's strategy. (Auth is deferred; the demo runs as a single tenant behind Basic Auth.)

## The Arize/Phoenix integration (track summary)

1. **Tracing** — `phoenix.otel.register(auto_instrument=True)` + the OpenInference ADK instrumentor → every agent/LLM/tool span in Phoenix Cloud.
2. **Evals** — an LLM-as-judge **groundedness** eval on every analysis + a **usefulness** (keep-rate) eval from feedback, both tenant-tagged.
3. **MCP** — `app/insights.py` wires the **Phoenix MCP server** (`@arizeai/phoenix-mcp`) into an ADK agent so it introspects its own traces/evals at runtime (pre-warmed at boot).
4. **Closed loop** — `app/learning.py` reads the tenant's graded keep/dismiss **from Phoenix** to drive the next scan: the agent improves from its own evaluation record.

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
| `POST /analyze` | Run the pipeline for `{company_url}`; merges results into the curated set, returns the workspace view + the run's new entrants. |
| `GET /workspace?url=` | The current curated set (kept shortlist + candidates), plus keep-rate. |
| `GET /company?url=` | A company's run history (snapshots, newest first). |
| `GET /companies` | All companies analyzed. |
| `GET /changes?url=` | Snapshot-to-snapshot diff (legacy; "new this run" supersedes it). |
| `POST /feedback` | Set an item's status (keep / dismiss / candidate); logged to Phoenix. |
| `POST /insights` | Ask the agent to introspect its own Phoenix telemetry via MCP. |
| `GET /health` | Liveness. |

## Project structure

```
market-agent/
├── app/
│   ├── agent.py          # ADK pipeline (profiler → competitive ∥ icp → synthesizer) + MarketAnalysis schema
│   ├── store.py          # MongoDB: curated items (merge + status), snapshots, change-diff
│   ├── evals.py          # LLM-as-judge groundedness eval
│   ├── learning.py       # Tier 2 — reads the next-scan learning signal from Phoenix
│   ├── observability.py  # Phoenix tracing + feedback/eval spans
│   └── insights.py       # Phoenix MCP self-reflection agent
├── server.py             # FastAPI (analyze, workspace, feedback, insights, …)
├── frontend/             # Next.js workspace UI (Netlify + Basic Auth middleware)
└── tests/
```

## License

[AGPL-3.0](../LICENSE). © 2026 Eliannah Linehan.
