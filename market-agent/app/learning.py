"""Tier 2: read the agent's learning signal from Phoenix (Arize as the engine).

The next run's preferences are sourced from the tenant's keep/dismiss history as
recorded in Phoenix (the user_feedback spans), so the agent literally improves
from its own evaluation record. Mongo is the fallback (and serves freshness for
back-to-back runs, where Phoenix's batch export hasn't indexed yet).
"""
import os

from app.store import company_key


def phoenix_configured() -> bool:
    return bool(
        os.environ.get("PHOENIX_API_KEY")
        and os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    )


def phoenix_preferences(tenant_id: str, company_url: str) -> str:
    """Build the preferences prompt from this tenant's feedback in Phoenix.

    Returns "" on any failure or if there's no graded history yet, so the caller
    falls back to Mongo.
    """
    if not phoenix_configured():
        return ""
    from phoenix.client import Client

    client = Client(
        base_url=os.environ["PHOENIX_COLLECTOR_ENDPOINT"],
        api_key=os.environ["PHOENIX_API_KEY"],
    )
    project = os.environ.get("PHOENIX_PROJECT_NAME", "market-agent")
    spans = client.spans.get_spans(
        project_identifier=project, name="user_feedback", limit=1000, timeout=20
    )

    key = company_key(company_url)
    # latest decision per (item_type, item_label), ordered by span start time
    latest: dict[tuple, tuple] = {}
    for s in spans:
        a = s.get("attributes", {})
        if a.get("tenant.id") != tenant_id or a.get("feedback.company") != key:
            continue
        item = (a.get("feedback.item_type"), a.get("feedback.item_label"))
        when = s.get("start_time") or ""
        if item not in latest or str(when) > str(latest[item][0]):
            latest[item] = (when, a.get("feedback.decision"))

    if not latest:
        return ""

    def names(item_type: str, decision: str) -> list[str]:
        return [
            lbl
            for (it, lbl), (_, dec) in latest.items()
            if it == item_type and dec == decision and lbl
        ]

    lines = []
    for it, dec, heading in [
        ("competitor", "keep", "Competitors they found relevant"),
        ("competitor", "dismiss", "Competitors they dismissed"),
        ("prospect", "keep", "Prospects they found relevant"),
        ("prospect", "dismiss", "Prospects they dismissed"),
    ]:
        vals = names(it, dec)
        if vals:
            lines.append(f"- {heading}: {', '.join(vals)}")
    return "\n".join(lines)
