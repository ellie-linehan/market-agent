from pydantic import BaseModel
from typing import Optional


class AnalysisRequest(BaseModel):
    company_url: str
    company_description: Optional[str] = None


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
