"""MongoDB persistence: every analysis is saved as a dated snapshot, keyed by
company, so a company becomes a workspace with a history rather than a one-shot."""
import os
import re
from datetime import datetime, timezone

from pymongo import MongoClient, DESCENDING

_client: MongoClient | None = None


def _db():
    global _client
    if _client is None:
        _client = MongoClient(os.environ["MONGODB_URI"])
    return _client[os.environ.get("MONGODB_DATABASE", "market_agent")]


def company_key(url: str) -> str:
    """Normalize a URL so 'https://www.ptg-usa.com/' and 'ptg-usa.com' collide."""
    k = url.strip().lower()
    k = re.sub(r"^https?://", "", k)
    k = re.sub(r"^www\.", "", k)
    return k.rstrip("/")


def save_snapshot(company_url: str, analysis: dict) -> dict:
    """Append one analysis snapshot for a company. Returns the stored snapshot."""
    doc = {
        "company_key": company_key(company_url),
        "company_url": company_url,
        "company_name": analysis.get("company") or company_key(company_url),
        "created_at": datetime.now(timezone.utc),
        "analysis": analysis,
    }
    result = _db().analyses.insert_one(doc)
    return {
        "id": str(result.inserted_id),
        "created_at": doc["created_at"],
        "company_url": doc["company_url"],
        "company_name": doc["company_name"],
        "analysis": analysis,
    }


def get_history(company_url: str) -> list[dict]:
    """All snapshots for a company, newest first."""
    cursor = _db().analyses.find({"company_key": company_key(company_url)}).sort(
        "created_at", DESCENDING
    )
    return [
        {
            "id": str(d["_id"]),
            "created_at": d["created_at"],
            "company_url": d.get("company_url"),
            "company_name": d.get("company_name"),
            "analysis": d["analysis"],
        }
        for d in cursor
    ]


def save_feedback(
    company_url: str, item_type: str, item_key: str, item_label: str, decision: str
) -> None:
    """Record a keep/dismiss on one competitor or prospect. Latest decision wins.

    Scoped to the company workspace (not an individual user), so feedback from
    multiple people at the same company aggregates into one signal.
    """
    key = company_key(company_url)
    filt = {"company_key": key, "item_type": item_type, "item_key": item_key}
    # Anything that isn't an explicit keep/dismiss clears the decision (toggle-off).
    if decision not in ("keep", "dismiss"):
        _db().feedback.delete_one(filt)
        return
    _db().feedback.update_one(
        filt,
        {
            "$set": {
                **filt,
                "item_label": item_label,
                "decision": decision,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


def get_feedback(company_url: str) -> list[dict]:
    """All keep/dismiss decisions for a company workspace."""
    return list(
        _db().feedback.find(
            {"company_key": company_key(company_url)},
            {"_id": 0, "company_key": 0},
        )
    )


def format_preferences(company_url: str) -> str:
    """Turn stored feedback into a prompt fragment the agents can honor.

    Returns "" when there is no feedback, so the agents run unchanged on a
    fresh workspace.
    """
    rows = get_feedback(company_url)
    if not rows:
        return ""

    def labels(item_type: str, decision: str) -> list[str]:
        return [
            r["item_label"]
            for r in rows
            if r["item_type"] == item_type and r["decision"] == decision
        ]

    lines = []
    mapping = [
        ("competitor", "keep", "Competitors they found relevant"),
        ("competitor", "dismiss", "Competitors they dismissed"),
        ("prospect", "keep", "Prospects they found relevant"),
        ("prospect", "dismiss", "Prospects they dismissed"),
    ]
    for item_type, decision, heading in mapping:
        vals = labels(item_type, decision)
        if vals:
            lines.append(f"- {heading}: {', '.join(vals)}")
    return "\n".join(lines)


def _norm_name(s: str | None) -> str:
    """Normalize a company name for identity matching: drop parentheticals and
    punctuation so 'LRS (PensionGold)' and 'LRS (Levi, Ray & Shoup)' collide."""
    s = (s or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)  # drop parentheticals
    s = re.sub(r"[^a-z0-9]+", " ", s)  # punctuation -> space
    return " ".join(s.split())


def _pricing_bucket(model: str | None) -> str:
    """Coarse pricing category, so reworded 'undisclosed' text isn't a 'change'."""
    m = (model or "").lower()
    if not m:
        return ""
    if "undisclosed" in m or "unknown" in m:
        return "undisclosed"
    if "freemium" in m or "free tier" in m or "free plan" in m:
        return "freemium"
    if "open source" in m:
        return "open-source"
    if "usage" in m or "per host" in m or "per gb" in m or "consumption" in m:
        return "usage"
    if "tiered" in m or ("free" in m and "pro" in m):
        return "tiered"
    if any(t in m for t in ("subscription", "/month", "/seat", "/user", "saas")):
        return "subscription"
    if any(t in m for t in ("enterprise", "custom", "rfp", "license")):
        return "enterprise"
    return "other"


def _competitor_key(c: dict) -> str:
    return _norm_name(c.get("name")) or _norm_name(c.get("url"))


def _prospect_key(p: dict) -> str:
    return _norm_name(p.get("company_name")) or _norm_name(p.get("website"))


def diff_analyses(prev: dict, curr: dict) -> dict:
    """What moved between two analyses: entrants, exits, and pricing shifts."""
    pc = {_competitor_key(c): c for c in prev.get("competitors", [])}
    cc = {_competitor_key(c): c for c in curr.get("competitors", [])}
    pricing_changed = []
    for key, comp in cc.items():
        if key in pc:
            before = _pricing_bucket(pc[key].get("pricing_model"))
            after = _pricing_bucket(comp.get("pricing_model"))
            if before and after and before != after:
                pricing_changed.append(
                    {"name": comp.get("name"), "from": pc[key].get("pricing_model"), "to": comp.get("pricing_model")}
                )

    pp = {_prospect_key(p): p for p in prev.get("icp_prospects", [])}
    cp = {_prospect_key(p): p for p in curr.get("icp_prospects", [])}

    return {
        "competitors_added": [cc[k] for k in cc if k and k not in pc],
        "competitors_removed": [pc[k] for k in pc if k and k not in cc],
        "pricing_changed": pricing_changed,
        "prospects_added": [cp[k] for k in cp if k and k not in pp],
        "prospects_removed": [pp[k] for k in pp if k and k not in cp],
    }


def get_changes(company_url: str) -> dict:
    """Diff the two most recent snapshots for a company workspace."""
    history = get_history(company_url)  # newest first
    if len(history) < 2:
        return {"has_prior": False}
    curr, prev = history[0], history[1]
    return {
        "has_prior": True,
        "from_date": prev["created_at"],
        "to_date": curr["created_at"],
        "diff": diff_analyses(prev["analysis"], curr["analysis"]),
    }


def list_companies() -> list[dict]:
    """One row per company with its latest timestamp and snapshot count."""
    pipeline = [
        {"$sort": {"created_at": DESCENDING}},
        {
            "$group": {
                "_id": "$company_key",
                "company_url": {"$first": "$company_url"},
                "company_name": {"$first": "$company_name"},
                "latest_at": {"$first": "$created_at"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"latest_at": DESCENDING}},
    ]
    return [
        {
            "company_key": d["_id"],
            "company_url": d["company_url"],
            "company_name": d["company_name"],
            "latest_at": d["latest_at"],
            "count": d["count"],
        }
        for d in _db().analyses.aggregate(pipeline)
    ]
