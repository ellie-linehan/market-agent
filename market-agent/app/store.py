"""MongoDB persistence: every analysis is saved as a dated snapshot, keyed by
company, so a company becomes a workspace with a history rather than a one-shot."""
import os
import re
from datetime import datetime, timezone

from pymongo import MongoClient, DESCENDING

_client: MongoClient | None = None


DEFAULT_TENANT = "demo"


def _db():
    global _client
    if _client is None:
        _client = MongoClient(os.environ["MONGODB_URI"])
    return _client[os.environ.get("MONGODB_DATABASE", "market_agent")]


def company_key(url: str) -> str:
    """Normalize a URL so 'https://www.acme.com/' and 'acme.com' collide."""
    k = url.strip().lower()
    k = re.sub(r"^https?://", "", k)
    k = re.sub(r"^www\.", "", k)
    return k.rstrip("/")


def save_snapshot(
    company_url: str,
    analysis: dict,
    evaluation: dict | None = None,
    span_id: str | None = None,
) -> dict:
    """Append one analysis snapshot for a company. Returns the stored snapshot."""
    doc = {
        "company_key": company_key(company_url),
        "company_url": company_url,
        "company_name": analysis.get("company") or company_key(company_url),
        "created_at": datetime.now(timezone.utc),
        "analysis": analysis,
        "eval": evaluation,
        "span_id": span_id,
    }
    result = _db().analyses.insert_one(doc)
    return {
        "id": str(result.inserted_id),
        "created_at": doc["created_at"],
        "company_url": doc["company_url"],
        "company_name": doc["company_name"],
        "analysis": analysis,
        "eval": evaluation,
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
            "eval": d.get("eval"),
        }
        for d in cursor
    ]


_NAME_STOP = {
    "and", "the", "of", "for", "a", "an",
    "inc", "incorporated", "llc", "llp", "ltd", "corp", "corporation", "co",
    "company", "group", "holdings", "services", "systems", "system",
    "solutions", "technologies", "technology", "partners", "software", "labs",
    "lab",
}
_NAME_PREFIXES = ("city of ", "town of ", "county of ")


def _norm_name(s: str | None) -> str:
    """Normalize a company/entity name for identity matching, so naming variants
    collide: 'Acme (Cloud)' ~ 'Acme (Hosted)', 'Globex' ~ 'Globex Group',
    'City of Springfield Board' ~ 'Springfield Board', 'X & Y' ~ 'X and Y'."""
    s = (s or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)  # drop parentheticals
    s = re.sub(r"[^a-z0-9]+", " ", s)  # punctuation/& -> space
    s = " ".join(s.split())
    for p in _NAME_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    toks = [t for t in s.split() if t not in _NAME_STOP]
    return " ".join(toks) or s


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


# --- Accumulate-and-curate item model (B) -------------------------------------
# A workspace keeps a persistent, deduped set of competitors/prospects across
# runs. Each item has a status: candidate (default, seen but not acted on),
# kept (pinned by the user), or dismissed (excluded). Analyze MERGES new
# findings in; it never replaces the set, so "no action" never means "dropped".

_ITEM_KEYFN = {"competitor": _competitor_key, "prospect": _prospect_key}


def merge_items(
    tenant_id: str, company_url: str, item_type: str, generated: list[dict]
) -> list[dict]:
    """Upsert generated items as candidates; preserve existing status. Returns
    the items that are genuinely new (first seen this run)."""
    key = company_key(company_url)
    keyfn = _ITEM_KEYFN[item_type]
    now = datetime.now(timezone.utc)
    new_items: list[dict] = []
    for it in generated:
        ik = keyfn(it)
        if not ik:
            continue
        res = _db().items.update_one(
            {"tenant_id": tenant_id, "company_key": key, "item_type": item_type, "item_key": ik},
            {
                "$set": {"data": it, "last_seen": now, "updated_at": now},
                "$setOnInsert": {
                    "tenant_id": tenant_id,
                    "company_key": key,
                    "item_type": item_type,
                    "item_key": ik,
                    "status": "candidate",
                    "first_seen": now,
                },
            },
            upsert=True,
        )
        if res.upserted_id is not None:
            new_items.append({**it, "item_key": ik})
    return new_items


def get_items(tenant_id: str, company_url: str, item_type: str) -> list[dict]:
    """Non-dismissed items, kept first then candidates (newest first within each)."""
    cursor = _db().items.find(
        {
            "tenant_id": tenant_id,
            "company_key": company_key(company_url),
            "item_type": item_type,
            "status": {"$ne": "dismissed"},
        }
    )
    order = {"kept": 0, "candidate": 1}
    rows = sorted(
        cursor,
        key=lambda r: (
            order.get(r.get("status"), 2),
            -(r["last_seen"].timestamp() if r.get("last_seen") else 0),
        ),
    )
    return [
        {
            **r.get("data", {}),
            "item_key": r["item_key"],
            "status": r.get("status", "candidate"),
            "reason": r.get("reason"),
        }
        for r in rows
    ]


def workspace_items(tenant_id: str, company_url: str) -> dict:
    return {
        "competitors": get_items(tenant_id, company_url, "competitor"),
        "prospects": get_items(tenant_id, company_url, "prospect"),
    }


def set_item_status(
    tenant_id: str,
    company_url: str,
    item_type: str,
    item_key: str,
    status: str,
    reason: str | None = None,
) -> None:
    """status: kept | dismissed | candidate ('candidate' clears a prior decision).
    reason: optional one-line 'why' — the generalizable learning signal."""
    updates = {"status": status, "updated_at": datetime.now(timezone.utc)}
    if reason:
        updates["reason"] = reason
    _db().items.update_one(
        {
            "tenant_id": tenant_id,
            "company_key": company_key(company_url),
            "item_type": item_type,
            "item_key": item_key,
        },
        {"$set": updates},
    )


def item_preferences(tenant_id: str, company_url: str) -> str:
    """Mongo-sourced preferences fallback (Tier 2 reads from Phoenix first)."""
    rows = list(
        _db().items.find(
            {
                "tenant_id": tenant_id,
                "company_key": company_key(company_url),
                "status": {"$in": ["kept", "dismissed"]},
            }
        )
    )
    if not rows:
        return ""

    def label(r: dict) -> str:
        d = r.get("data", {})
        return d.get("name") or d.get("company_name") or r["item_key"]

    def names(item_type: str, status: str) -> list[str]:
        return [label(r) for r in rows if r["item_type"] == item_type and r["status"] == status]

    lines = []
    for it, st, heading in [
        ("competitor", "kept", "Competitors they found relevant"),
        ("competitor", "dismissed", "Competitors they dismissed"),
        ("prospect", "kept", "Prospects they found relevant"),
        ("prospect", "dismissed", "Prospects they dismissed"),
    ]:
        vals = names(it, st)
        if vals:
            lines.append(f"- {heading}: {', '.join(vals)}")
    return "\n".join(lines)


def keep_rate(tenant_id: str, company_url: str) -> dict:
    """Per-workspace usefulness signal: kept vs dismissed counts + rate."""
    base = {"tenant_id": tenant_id, "company_key": company_key(company_url)}
    kept = _db().items.count_documents({**base, "status": "kept"})
    dismissed = _db().items.count_documents({**base, "status": "dismissed"})
    decided = kept + dismissed
    return {"kept": kept, "dismissed": dismissed, "keep_rate": (kept / decided) if decided else None}


def latest_span_id(tenant_id: str, company_url: str) -> str | None:
    """span_id of the most recent analysis run, so feedback can be annotated onto
    that analysis trace in Phoenix."""
    doc = _db().analyses.find_one(
        {"company_key": company_key(company_url)},
        sort=[("created_at", DESCENDING)],
        projection={"span_id": 1},
    )
    return doc.get("span_id") if doc else None


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
