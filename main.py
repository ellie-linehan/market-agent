from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

load_dotenv(override=True)

from models.schemas import AnalysisRequest, MarketAnalysis
from agent.market_agent import run_analysis
from agent.observability import setup_arize


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_arize()
    yield


app = FastAPI(title="B2B Market Intelligence Agent", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=MarketAnalysis)
async def analyze(request: AnalysisRequest):
    try:
        return await run_analysis(request.company_url, request.company_description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
