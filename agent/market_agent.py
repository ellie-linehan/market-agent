import os
import json
from google import genai
from google.genai import types
from elasticsearch import AsyncElasticsearch
from motor.motor_asyncio import AsyncIOMotorClient
from models.schemas import MarketAnalysis
from agent.tools.competitive import search_competitors
from agent.tools.icp import find_matching_prospects
from agent.observability import get_tracer

_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

_SYSTEM_PROMPT = """You are a B2B market intelligence agent for SaaS founders.

Given a company URL or description, you:
1. Map the competitive landscape: identify direct competitors, their positioning, target segments, and pricing models.
2. Build an ICP (Ideal Customer Profile) and surface prospect companies that match it.
3. Synthesize a concise market summary with one actionable insight the founder can use today.

Use the provided index data when available. Fill gaps with your world knowledge.
For optional fields you cannot determine, use null. Never fabricate specifics."""


async def _fetch_context(query: str) -> tuple[list, list]:
    competitors_raw, prospects_raw = [], []
    try:
        es = AsyncElasticsearch(
            cloud_id=os.environ["ELASTIC_CLOUD_ID"],
            api_key=os.environ["ELASTIC_API_KEY"],
        )
        competitors_raw = await search_competitors(query, es)
    except Exception:
        pass
    try:
        mongo_client = AsyncIOMotorClient(os.environ["MONGODB_URI"])
        db = mongo_client[os.environ.get("MONGODB_DATABASE", "market_agent")]
        prospects_raw = await find_matching_prospects({"indexed": True}, db)
    except Exception:
        pass
    return competitors_raw, prospects_raw


async def run_analysis(company_url: str, company_description: str | None) -> MarketAnalysis:
    query = company_description or company_url
    competitors_raw, prospects_raw = await _fetch_context(query)

    prompt = f"""Company: {company_url}
Description: {company_description or "not provided"}

Indexed competitor data (may be empty):
{json.dumps(competitors_raw, default=str)}

Indexed prospect data (may be empty):
{json.dumps(prospects_raw, default=str)}

Return a complete market analysis for this company."""

    tracer = get_tracer()
    with tracer.start_as_current_span("gemini.market_analysis") as span:
        span.set_attribute("company.url", company_url)
        span.set_attribute("context.competitors_found", len(competitors_raw))
        span.set_attribute("context.prospects_found", len(prospects_raw))

        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        response = await _client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=MarketAnalysis,
            ),
        )

        span.set_attribute("llm.model_name", model)
        span.set_attribute("llm.token_count.prompt", response.usage_metadata.prompt_token_count)
        span.set_attribute("llm.token_count.completion", response.usage_metadata.candidates_token_count)
        span.set_attribute("llm.token_count.total", response.usage_metadata.total_token_count)

    return MarketAnalysis.model_validate_json(response.text)
