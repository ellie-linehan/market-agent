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
