import os
import re
import json
from dotenv import load_dotenv
from google.adk.agents import Agent, ParallelAgent, SequentialAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

load_dotenv(override=True)

from app.observability import setup_arize
setup_arize()

_model = Gemini(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    retry_options=types.HttpRetryOptions(attempts=3),
)


def fetch_company_website(url: str) -> str:
    """Fetch the homepage of a company website and return its visible text content.

    Args:
        url: The company URL to fetch (e.g. 'https://thrixel.com').

    Returns:
        Visible text from the homepage, truncated to 3000 characters.
    """
    import httpx
    try:
        if not url.startswith("http"):
            url = "https://" + url
        resp = httpx.get(url, timeout=10, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (compatible; MarketIntelligenceBot/1.0)"
        })
        html = resp.text
        # Strip scripts, styles, and tags
        html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:3000] if text else "Could not extract text from page."
    except Exception as e:
        return f"Could not fetch {url}: {e}"


def search_competitors(company_description: str) -> str:
    """Search for B2B SaaS companies competing in the same space as the given company.

    Args:
        company_description: Description of the company or product to find competitors for.

    Returns:
        A JSON string listing competitor companies found, or a fallback message.
    """
    try:
        from elasticsearch import Elasticsearch
        es = Elasticsearch(
            cloud_id=os.environ["ELASTIC_CLOUD_ID"],
            api_key=os.environ["ELASTIC_API_KEY"],
        )
        resp = es.search(
            index="companies",
            query={
                "multi_match": {
                    "query": company_description,
                    "fields": ["description", "positioning", "category"],
                }
            },
            size=5,
        )
        results = [hit["_source"] for hit in resp["hits"]["hits"]]
        return json.dumps(results) if results else "No competitors in index — use world knowledge."
    except Exception:
        return "Competitor index unavailable — use world knowledge."


def find_icp_prospects(target_company_url: str) -> str:
    """Retrieve previously saved ICP prospects for a specific company.

    Args:
        target_company_url: The URL of the company being analyzed (used to scope results).

    Returns:
        A JSON string listing prospect companies saved for this company, or a message if none exist.
    """
    try:
        from pymongo import MongoClient
        client = MongoClient(os.environ["MONGODB_URI"])
        db = client[os.environ.get("MONGODB_DATABASE", "market_agent")]
        prospects = list(db.prospects.find({"target_company_url": target_company_url}, {"_id": 0}).limit(10))
        if prospects:
            return json.dumps(prospects)
        return "No prospects stored yet for this company — identify from world knowledge and save with save_prospect."
    except Exception:
        return "Prospect database unavailable — identify prospects from world knowledge."


def save_prospect(
    target_company_url: str,
    company_name: str,
    website: str,
    match_reason: str,
    industry: str = "",
    employee_count: str = "",
) -> str:
    """Save a company as an ICP-matched prospect for a specific analysis.

    Args:
        target_company_url: The URL of the company being analyzed (scopes this prospect to that analysis).
        company_name: Name of the prospect company.
        website: Website URL of the prospect company.
        match_reason: Why this company matches the ICP.
        industry: Industry the company operates in.
        employee_count: Approximate employee count (e.g. '50-200').

    Returns:
        Confirmation message.
    """
    try:
        from pymongo import MongoClient
        client = MongoClient(os.environ["MONGODB_URI"])
        db = client[os.environ.get("MONGODB_DATABASE", "market_agent")]
        db.prospects.update_one(
            {"target_company_url": target_company_url, "website": website},
            {"$set": {
                "target_company_url": target_company_url,
                "company_name": company_name,
                "website": website,
                "match_reason": match_reason,
                "industry": industry,
                "employee_count": employee_count,
            }},
            upsert=True,
        )
        return f"Saved {company_name} ({website}) as an ICP prospect."
    except Exception as e:
        return f"Could not save prospect: {e}"


competitive_agent = Agent(
    name="competitive_agent",
    model=_model,
    instruction="""You are a competitive intelligence specialist for B2B SaaS.

When given a company URL or description:
1. Call fetch_company_website with the URL to read the company's homepage and understand what they do.
2. Call search_competitors to check the database for known competitors.
3. Using what you learned from the website and your world knowledge, identify the top 5 direct competitors.
4. For each competitor provide: name, URL, positioning, target segment, key features, and pricing model.
5. Return a structured competitive landscape summary.

Never ask for clarification. Always fetch the website first, then produce a complete analysis.""",
    tools=[fetch_company_website, search_competitors],
)

icp_agent = Agent(
    name="icp_agent",
    model=_model,
    instruction="""You are an ICP (Ideal Customer Profile) research specialist for B2B SaaS.

When given a company URL or description:
1. Call fetch_company_website with the URL to read the company's homepage and understand what they do.
2. Call find_icp_prospects with the company URL to check for any previously saved prospects for this specific company.
3. Using what you learned from the website and your world knowledge, define the ICP and identify 5-10 matching prospect companies.
4. Call save_prospect for each new prospect, passing the target_company_url so results are scoped to this analysis.
5. Return a structured ICP definition and prospect list with match reasons.

Never ask for clarification. Always fetch the website first, then produce a complete analysis.""",
    tools=[fetch_company_website, find_icp_prospects, save_prospect],
)

parallel_research = ParallelAgent(
    name="parallel_research",
    sub_agents=[competitive_agent, icp_agent],
)

synthesizer = Agent(
    name="synthesizer",
    model=_model,
    instruction="""You are a B2B market intelligence analyst for SaaS founders.

Two specialist agents have just completed their research in parallel:
- competitive_agent analyzed the competitive landscape
- icp_agent identified the ICP and prospect companies

Synthesize their outputs into a single unified market analysis:
- **Competitive Landscape**: Top 5 competitors with positioning and key differentiators
- **ICP**: Clear definition of the ideal customer
- **Top Prospects**: Companies matching the ICP with reasons why
- **Insight**: One actionable move the founder can make this week""",
)

root_agent = SequentialAgent(
    name="market_intelligence_agent",
    sub_agents=[parallel_research, synthesizer],
)

app = App(
    root_agent=root_agent,
    name="app",
)
