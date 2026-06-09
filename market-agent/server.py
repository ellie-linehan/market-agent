import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True)

from app import store, insights, evals
from app.observability import log_feedback, log_eval
from app.agent import root_agent, MarketAnalysis
from google.adk.runners import InMemoryRunner
from google.genai import types

_APP_NAME = "market-agent"
_runner = InMemoryRunner(agent=root_agent, app_name=_APP_NAME)
_insights_runner: InMemoryRunner | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm the Phoenix MCP connection at boot so the first /insights call
    doesn't pay the npx cold-start race. Never blocks startup on failure."""
    global _insights_runner
    if insights.phoenix_configured():
        try:
            runner = InMemoryRunner(
                agent=insights.build_insights_agent(), app_name="insights"
            )
            # spawn npx + complete the MCP handshake now (slow boot is fine)
            await asyncio.wait_for(runner.agent.tools[0].get_tools(), timeout=90)
            _insights_runner = runner
            print("[insights] Phoenix MCP pre-warmed")
        except Exception as e:  # noqa: BLE001 - degrade to lazy init on the endpoint
            print(f"[insights] Phoenix MCP pre-warm skipped: {e}")
    yield


app = FastAPI(title="B2B Market Intelligence Agent", lifespan=lifespan)

# The Netlify frontend calls this backend directly (browser → Cloud Run) to avoid
# serverless function timeouts on the ~60s /analyze. Allow its origin.
# CORS_ALLOW_ORIGINS = comma-separated origins, or "*" (default).
_origins = os.environ.get("CORS_ALLOW_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins == "*" else [o.strip() for o in _origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    company_url: str
    company_description: str | None = None


class FeedbackRequest(BaseModel):
    company_url: str
    item_type: str  # "competitor" | "prospect"
    item_key: str
    item_label: str
    decision: str  # "keep" | "dismiss"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    tenant = store.DEFAULT_TENANT
    session_id = uuid.uuid4().hex
    # Fold in this workspace's accumulated keep/dismiss so the agents weight
    # toward what the founder keeps and away from what they dismiss.
    # (Phase 4 reads this from Phoenix; Mongo is the current source/fallback.)
    preferences = await asyncio.to_thread(store.item_preferences, tenant, req.company_url)
    await _runner.session_service.create_session(
        app_name=_APP_NAME,
        user_id="web",
        session_id=session_id,
        state={"preferences": preferences},
    )
    text = req.company_url
    if req.company_description:
        text = f"{req.company_url}\n{req.company_description}"
    msg = types.Content(role="user", parts=[types.Part(text=text)])

    final = None
    async for ev in _runner.run_async(
        user_id="web", session_id=session_id, new_message=msg
    ):
        if ev.author == "synthesizer" and ev.content and ev.content.parts:
            for part in ev.content.parts:
                if getattr(part, "text", None):
                    final = part.text

    if not final:
        raise HTTPException(status_code=500, detail="No analysis produced")

    analysis = MarketAnalysis.model_validate_json(final)

    # LLM-as-judge groundedness eval (best-effort): score the analysis against
    # the profiler's verified company profile, log it to Phoenix, store on snapshot.
    evaluation = None
    try:
        session = await _runner.session_service.get_session(
            app_name=_APP_NAME, user_id="web", session_id=session_id
        )
        profile = (session.state.get("profile") if session else "") or ""
        if profile:
            result = await asyncio.to_thread(
                evals.grounded_score,
                profile,
                analysis.company,
                [c.name for c in analysis.competitors],
                analysis.market_summary,
            )
            evaluation = result.model_dump()
            log_eval(
                "groundedness",
                tenant,
                analysis.company,
                result.score,
                result.label,
                result.reason,
            )
    except Exception:  # noqa: BLE001 - eval is best-effort, never break analysis
        evaluation = None

    # Merge the generated lists into the persistent curated set (accumulate, not
    # replace) and snapshot the run (summary + eval) for the history timeline.
    new_c = await asyncio.to_thread(
        store.merge_items, tenant, req.company_url, "competitor",
        [c.model_dump() for c in analysis.competitors],
    )
    new_p = await asyncio.to_thread(
        store.merge_items, tenant, req.company_url, "prospect",
        [p.model_dump() for p in analysis.icp_prospects],
    )
    await asyncio.to_thread(
        store.save_snapshot, req.company_url, analysis.model_dump(), evaluation
    )

    view = await asyncio.to_thread(store.workspace_items, tenant, req.company_url)
    return {
        "company": analysis.company,
        "market_summary": analysis.market_summary,
        "eval": evaluation,
        "competitors": view["competitors"],
        "icp_prospects": view["prospects"],
        "new_competitors": [c.get("name") for c in new_c],
        "new_prospects": [p.get("company_name") for p in new_p],
    }


@app.get("/workspace")
async def workspace(url: str):
    """Load the merged curated set (kept + candidates, dismissed excluded)."""
    tenant = store.DEFAULT_TENANT
    view = await asyncio.to_thread(store.workspace_items, tenant, url)
    return {
        "company_url": url,
        "competitors": view["competitors"],
        "icp_prospects": view["prospects"],
        "keep_rate": await asyncio.to_thread(store.keep_rate, tenant, url),
    }


@app.get("/company")
async def company(url: str):
    """Load a company's workspace: every saved snapshot, newest first."""
    history = await asyncio.to_thread(store.get_history, url)
    return {"company_url": url, "history": history}


@app.get("/companies")
async def companies():
    """List every company that has at least one saved analysis."""
    return {"companies": await asyncio.to_thread(store.list_companies)}


@app.get("/changes")
async def changes(url: str):
    """What changed between the two most recent analyses of a company."""
    return await asyncio.to_thread(store.get_changes, url)


class InsightsRequest(BaseModel):
    question: str


@app.post("/insights")
async def insights_endpoint(req: InsightsRequest):
    """Ask the agent to introspect its own telemetry via the Phoenix MCP server."""
    global _insights_runner
    if not insights.phoenix_configured():
        raise HTTPException(
            status_code=400,
            detail="Phoenix not configured (set PHOENIX_API_KEY and PHOENIX_COLLECTOR_ENDPOINT).",
        )
    msg = types.Content(role="user", parts=[types.Part(text=req.question)])

    async def _run(runner: InMemoryRunner) -> str:
        session_id = uuid.uuid4().hex
        await runner.session_service.create_session(
            app_name="insights", user_id="web", session_id=session_id
        )
        answer = ""
        async for ev in runner.run_async(
            user_id="web", session_id=session_id, new_message=msg
        ):
            if ev.content and ev.content.parts:
                for part in ev.content.parts:
                    if getattr(part, "text", None):
                        answer = part.text
        return answer

    # MCP-over-stdio is intermittently flaky on Windows (cold-start races, and
    # pipe-buffer hangs on larger responses). Bound each attempt with a timeout
    # and retry once with a fresh runner so the endpoint never stalls.
    last_err: Exception | None = None
    for _ in range(2):
        if _insights_runner is None:
            _insights_runner = InMemoryRunner(
                agent=insights.build_insights_agent(), app_name="insights"
            )
        try:
            answer = await asyncio.wait_for(_run(_insights_runner), timeout=60)
            return {"answer": answer}
        except Exception as e:  # noqa: BLE001 - incl. TimeoutError; retry fresh
            last_err = e
            _insights_runner = None

    raise HTTPException(
        status_code=504, detail=f"Phoenix MCP call timed out / failed: {last_err}"
    )


@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    """Set an item's curated status (keep=pin, dismiss=hide, else candidate) and
    log the signal to Phoenix as tenant-tagged human feedback."""
    tenant = store.DEFAULT_TENANT
    status = {"keep": "kept", "dismiss": "dismissed"}.get(req.decision, "candidate")
    await asyncio.to_thread(
        store.set_item_status, tenant, req.company_url, req.item_type, req.item_key, status
    )
    log_feedback(
        tenant,
        store.company_key(req.company_url),
        req.item_type,
        req.item_key,
        req.item_label,
        req.decision,
    )
    # Tier 1: track the per-workspace usefulness signal (keep-rate) in Phoenix
    # alongside groundedness, so the agent is measured on both axes over time.
    kr = await asyncio.to_thread(store.keep_rate, tenant, req.company_url)
    if kr["keep_rate"] is not None:
        log_eval(
            "usefulness",
            tenant,
            store.company_key(req.company_url),
            kr["keep_rate"],
            "useful" if kr["keep_rate"] >= 0.5 else "low",
            f"{kr['kept']} kept / {kr['dismissed']} dismissed",
        )
    return {"ok": True}
