"""Phoenix (Arize) tracing for the ADK agent.

The Arize hackathon track uses Phoenix (Phoenix Cloud / self-hosted), NOT Arize
AX. We send OpenInference traces via phoenix.otel.register(auto_instrument=True),
which picks up openinference-instrumentation-google-adk automatically.
"""
import os

from opentelemetry import trace


def setup_phoenix() -> None:
    """Register Phoenix tracing. No-ops if PHOENIX_API_KEY is unset so the app
    still runs locally without observability configured.

    Reads (set these in .env):
      PHOENIX_API_KEY            e.g. px_live_...
      PHOENIX_COLLECTOR_ENDPOINT e.g. https://app.phoenix.arize.com/s/<space>
      PHOENIX_PROJECT_NAME       optional, defaults to "market-agent"
    """
    if not os.environ.get("PHOENIX_API_KEY"):
        return

    from phoenix.otel import register

    register(
        project_name=os.environ.get("PHOENIX_PROJECT_NAME", "market-agent"),
        auto_instrument=True,  # discovers openinference-instrumentation-google-adk
        batch=True,
        set_global_tracer_provider=True,
    )


_px_client = None


def flush_traces() -> None:
    """Push buffered spans to Phoenix so they can be annotated by span_id."""
    try:
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush()
    except Exception:  # noqa: BLE001
        pass


def annotate_span(
    span_id: str,
    name: str,
    *,
    label: str | None = None,
    score: float | None = None,
    explanation: str | None = None,
    kind: str = "CODE",
) -> None:
    """Attach an eval / feedback annotation to an existing span so it shows in
    Phoenix's Annotations tab (the Arize-native view). Best-effort."""
    global _px_client
    if not span_id or not os.environ.get("PHOENIX_API_KEY"):
        return
    try:
        if _px_client is None:
            from phoenix.client import Client

            _px_client = Client(
                base_url=os.environ["PHOENIX_COLLECTOR_ENDPOINT"],
                api_key=os.environ["PHOENIX_API_KEY"],
            )
        _px_client.spans.add_span_annotation(
            span_id=span_id,
            annotation_name=name,
            annotator_kind=kind,
            label=label,
            score=score,
            explanation=explanation,
        )
    except Exception:  # noqa: BLE001 - never break the request on observability
        pass


def log_eval(
    name: str, tenant_id: str, company: str, score: float, label: str, reason: str
) -> None:
    """Emit an eval result (machine groundedness or human usefulness) as a
    tenant-tagged span so it lands in Phoenix alongside the agent traces."""
    tracer = trace.get_tracer("market-agent.eval")
    with tracer.start_as_current_span(f"eval.{name}") as span:
        span.set_attribute("eval.name", name)
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("eval.company", company)
        span.set_attribute("eval.score", score)
        span.set_attribute("eval.label", label)
        span.set_attribute("eval.explanation", reason)


def log_feedback(
    tenant_id: str,
    company: str,
    item_type: str,
    item_key: str,
    item_label: str,
    decision: str,
) -> None:
    """Emit a tenant-tagged user-feedback span so keep/dismiss flows into Phoenix
    as the human-feedback layer of the self-improvement loop."""
    tracer = trace.get_tracer("market-agent.feedback")
    with tracer.start_as_current_span("user_feedback") as span:
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("feedback.company", company)
        span.set_attribute("feedback.item_type", item_type)
        span.set_attribute("feedback.item_key", item_key)
        span.set_attribute("feedback.item_label", item_label)
        span.set_attribute("feedback.decision", decision)
        # numeric score so Phoenix can aggregate a usefulness metric
        span.set_attribute("feedback.score", 1.0 if decision == "keep" else 0.0)
