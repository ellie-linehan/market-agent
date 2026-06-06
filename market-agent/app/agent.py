import os
import re
from typing import Optional
from dotenv import load_dotenv
from google.adk.agents import Agent, ParallelAgent, SequentialAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel

load_dotenv(override=True)

from app.observability import setup_arize
setup_arize()

_model = Gemini(
    model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
    retry_options=types.HttpRetryOptions(attempts=3),
)


# --- Structured output (mirrors models/schemas.py the frontend renders) ---
class Competitor(BaseModel):
    name: str
    url: str
    positioning: str
    target_segment: str
    key_features: list[str]
    pricing_model: Optional[str] = None


class ICPSignal(BaseModel):
    company_name: str
    website: str
    match_reason: str
    employee_count: Optional[str] = None
    industry: Optional[str] = None
    tech_stack: list[str] = []


class MarketAnalysis(BaseModel):
    company: str
    competitors: list[Competitor]
    icp_prospects: list[ICPSignal]
    market_summary: str


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

        # Always extract <title> and <meta> tags first — these are server-rendered
        # even on JS-heavy sites and give the most reliable signal about what the company does.
        meta_parts = []
        title = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if title:
            meta_parts.append(f"Title: {title.group(1).strip()}")
        for attr in ("description", "og:description", "og:title", "twitter:description"):
            m = re.search(rf'<meta[^>]+(?:name|property)="{attr}"[^>]+content="([^"]+)"', html, re.IGNORECASE)
            if not m:
                m = re.search(rf'<meta[^>]+content="([^"]+)"[^>]+(?:name|property)="{attr}"', html, re.IGNORECASE)
            if m:
                meta_parts.append(f"{attr}: {m.group(1).strip()}")

        # Strip scripts, styles, then all tags for body text
        body = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()

        combined = "\n".join(meta_parts)
        if body:
            combined += "\n\n" + body
        return combined[:3000] if combined else "Could not extract text from page."
    except Exception as e:
        return f"Could not fetch {url}: {e}"


# Step 1: establish company identity ONCE, grounded in the fetched site.
# This is the fix for domain-name hallucination (e.g. "PTG" -> machining vs. pension software):
# downstream agents read this profile instead of re-interpreting the raw URL.
profiler_agent = Agent(
    name="profiler_agent",
    model=_model,
    instruction="""You are a company analyst.

1. Call fetch_company_website with the given URL.
2. The tool returns Title, og:title, and homepage text. These are authoritative — they tell you exactly what this company does. Ignore any prior association you have with the domain name or an abbreviation inside it. Do not guess what an abbreviation stands for from memory; read what the site actually says.
3. Write a concise profile of the company: its real name, what it sells, the industry/category it operates in, and who its customers are. Ground every claim in the fetched text. If the site is sparse, say so — do not invent.

Output only the profile. Never ask for clarification.""",
    tools=[fetch_company_website],
    output_key="profile",
)

# competitive/icp instructions are providers (not static strings) so they can
# fold in per-workspace user feedback ("preferences") when present, and degrade
# cleanly to no-feedback when it's absent (e.g. in the ADK playground).
def _preferences_suffix(ctx, noun: str) -> str:
    prefs = ctx.state.get("preferences", "")
    if not prefs:
        return ""
    return (
        f"\n\nThe founder has reviewed past {noun} suggestions and given feedback:\n"
        f"{prefs}\n"
        f"Weight your selection toward {noun}s like the ones they KEPT and away from "
        f"the kinds they DISMISSED. This is their judgment about their own market — honor it."
    )


def _competitive_instruction(ctx) -> str:
    profile = ctx.state.get("profile", "")
    return f"""You are a competitive intelligence specialist for B2B companies.

Here is a verified profile of the target company:
{profile}

Identify the top 5 direct competitors of THIS company as described in the profile above — not of any other company that shares a similar name or abbreviation. Use your own knowledge of this market.

For each competitor be precise — no vague marketing language:
- name and url
- positioning: their core differentiator in one sentence
- target_segment: the specific buyer profile (e.g. "mid-size US public pension funds, 10k-100k members") — not just "enterprise" or "SMB"
- key_features: 3-5 features that actually set them apart from the field
- pricing_model: real tiers and numbers where known; write "undisclosed" only if genuinely unknown

Never ask for clarification.""" + _preferences_suffix(ctx, "competitor")


def _icp_instruction(ctx) -> str:
    profile = ctx.state.get("profile", "")
    return f"""You are an ICP research specialist for B2B founders.

Here is a verified profile of the target company:
{profile}

Define the Ideal Customer Profile for THIS company with concrete, filterable criteria — specific enough to build a prospecting list:
- Company stage and size
- Team or operational signals
- Tech-stack or systems indicators that signal fit
- The buying trigger that creates urgency (a funding round, compliance deadline, leadership change, etc.)

Then identify 5-10 real prospect companies that fit. For each, cite a specific reason they match — a concrete signal, not generic fit. Include company name, website, industry, and approximate size where known.

Output should be specific enough that the founder could write targeted cold outreach from it. Never ask for clarification.""" + _preferences_suffix(ctx, "prospect")


competitive_agent = Agent(
    name="competitive_agent",
    model=_model,
    instruction=_competitive_instruction,
    output_key="competitive",
)

icp_agent = Agent(
    name="icp_agent",
    model=_model,
    instruction=_icp_instruction,
    output_key="icp",
)

parallel_research = ParallelAgent(
    name="parallel_research",
    sub_agents=[competitive_agent, icp_agent],
)

synthesizer = Agent(
    name="synthesizer",
    model=_model,
    instruction="""You are a B2B market intelligence analyst. You are given research from three steps:

COMPANY PROFILE:
{profile}

COMPETITIVE RESEARCH:
{competitive}

ICP AND PROSPECTS:
{icp}

Produce the final structured market analysis:
- company: the name of the company from the profile.
- competitors: the competitors from the competitive research, each with positioning, target_segment, key_features, and pricing_model.
- icp_prospects: the prospect companies from the ICP research, each with company_name, website, match_reason, and industry / employee_count / tech_stack where known.
- market_summary: 3-4 tight sentences on market dynamics and the clearest gap this company can own, then one final sentence that starts with "Actionable insight:" naming a specific segment, competitor, or customer type to act on this week.

Ground everything in the research provided. Do not invent competitors or prospects that were not researched. Cut the filler.""",
    output_schema=MarketAnalysis,
    output_key="analysis",
)

root_agent = SequentialAgent(
    name="market_intelligence_agent",
    sub_agents=[profiler_agent, parallel_research, synthesizer],
)

app = App(
    root_agent=root_agent,
    name="app",
)
