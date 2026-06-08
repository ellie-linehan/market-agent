"""LLM-as-judge groundedness eval.

Scores whether a produced market analysis is grounded in the verified company
profile (from the site) — i.e. is it about the RIGHT company, with plausible
competitors — or hallucinated from the domain name. This is the machine quality
floor that complements the human keep/dismiss feedback loop.
"""
import os

from pydantic import BaseModel
from google import genai
from google.genai import types

_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


class GroundednessEval(BaseModel):
    score: float  # 0.0 (hallucinated) .. 1.0 (fully grounded)
    label: str  # "grounded" | "partial" | "hallucinated"
    reason: str


def grounded_score(
    profile: str, company: str, competitors: list[str], summary: str
) -> GroundednessEval:
    prompt = f"""You are evaluating whether a market analysis is grounded in the
verified facts about a company.

VERIFIED COMPANY PROFILE (from the company's own website):
{profile}

THE ANALYSIS UNDER REVIEW:
- Company identified as: {company}
- Competitors listed: {", ".join(competitors) or "(none)"}
- Market summary: {summary}

Rate how well the analysis is GROUNDED in the verified profile:
- Is it about the SAME company the profile describes (right industry and product),
  not a different company that merely shares a name or abbreviation?
- Are the competitors plausible for THIS company's actual market?

score: 0.0 (completely hallucinated — wrong company/industry) to 1.0 (fully grounded).
label: "grounded" (score >= 0.8), "partial" (0.4-0.8), or "hallucinated" (< 0.4).
reason: one sentence citing the specific match or mismatch."""

    resp = _client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GroundednessEval,
        ),
    )
    return GroundednessEval.model_validate_json(resp.text)
