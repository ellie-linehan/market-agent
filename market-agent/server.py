import asyncio
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True)

from app import store
from app.observability import log_feedback
from app.agent import root_agent, MarketAnalysis
from google.adk.runners import InMemoryRunner
from google.genai import types

_APP_NAME = "market-agent"
_runner = InMemoryRunner(agent=root_agent, app_name=_APP_NAME)

app = FastAPI(title="B2B Market Intelligence Agent")


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


@app.post("/analyze", response_model=MarketAnalysis)
async def analyze(req: AnalyzeRequest) -> MarketAnalysis:
    session_id = uuid.uuid4().hex
    # Fold in this workspace's accumulated keep/dismiss feedback so the agents
    # weight toward what the founder keeps and away from what they dismiss.
    preferences = await asyncio.to_thread(store.format_preferences, req.company_url)
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
    await asyncio.to_thread(store.save_snapshot, req.company_url, analysis.model_dump())
    return analysis


@app.get("/company")
async def company(url: str):
    """Load a company's workspace: every saved snapshot, newest first."""
    history = await asyncio.to_thread(store.get_history, url)
    return {"company_url": url, "history": history}


@app.get("/companies")
async def companies():
    """List every company that has at least one saved analysis."""
    return {"companies": await asyncio.to_thread(store.list_companies)}


@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    """Record a keep/dismiss and log it to Arize as human-feedback signal."""
    await asyncio.to_thread(
        store.save_feedback,
        req.company_url,
        req.item_type,
        req.item_key,
        req.item_label,
        req.decision,
    )
    log_feedback(
        store.company_key(req.company_url),
        req.item_type,
        req.item_key,
        req.item_label,
        req.decision,
    )
    return {"ok": True}


@app.get("/feedback")
async def get_feedback(url: str):
    """All keep/dismiss decisions for a company workspace."""
    return {"feedback": await asyncio.to_thread(store.get_feedback, url)}
