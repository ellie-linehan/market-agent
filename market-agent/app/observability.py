import os
from typing import Sequence
from opentelemetry.sdk.trace import SpanProcessor, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Span

_AGENT_PARENTS: dict[str, str | None] = {
    "market_intelligence_agent": None,
    "profiler_agent": "market_intelligence_agent",
    "parallel_research": "market_intelligence_agent",
    "competitive_agent": "parallel_research",
    "icp_agent": "parallel_research",
    "synthesizer": "market_intelligence_agent",
}

_INVOKE_PREFIX = "invoke_agent "


class ArizeEnrichmentProcessor(SpanProcessor):
    """Adds Arize routing, graph node, and session attributes to ADK spans.

    - arize.project.name  → routes spans to the correct Arize project
    - graph.node.id / graph.node.parent_id → powers Agent Graph + Path views
    - session.id (copied from gen_ai.conversation.id) → powers Sessions view
      Note: gen_ai.conversation.id is set by ADK *after* on_start fires,
      so we copy it in a separate exporter wrapper at export time instead.
    """

    def __init__(self, project_name: str) -> None:
        self._project_name = project_name

    def on_start(self, span: Span, parent_context=None) -> None:
        span.set_attribute("arize.project.name", self._project_name)

        name = span.name
        if not name.startswith(_INVOKE_PREFIX):
            return

        agent_name = name[len(_INVOKE_PREFIX):]
        if agent_name not in _AGENT_PARENTS:
            return

        span.set_attribute("graph.node.id", agent_name)
        span.set_attribute(
            "graph.node.display_name",
            agent_name.replace("_", " ").title(),
        )
        parent = _AGENT_PARENTS[agent_name]
        if parent:
            span.set_attribute("graph.node.parent_id", parent)

    def on_end(self, span: ReadableSpan) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class SessionMappingExporter(SpanExporter):
    """Wraps another exporter and copies gen_ai.conversation.id → session.id."""

    def __init__(self, wrapped: SpanExporter) -> None:
        self._wrapped = wrapped

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            attrs = span.attributes or {}
            conv_id = attrs.get("gen_ai.conversation.id")
            if conv_id and "session.id" not in attrs:
                new_attrs = dict(attrs)
                new_attrs["session.id"] = conv_id
                object.__setattr__(span, "_attributes", new_attrs)
        return self._wrapped.export(spans)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)


def log_feedback(
    company: str, item_type: str, item_key: str, item_label: str, decision: str
) -> None:
    """Emit a user-feedback span so keep/dismiss signal flows into Arize.

    The enrichment processor stamps arize.project.name on every span, so this
    lands in the same project as the agent traces and becomes the human-feedback
    layer of the eval story.
    """
    from opentelemetry import trace

    tracer = trace.get_tracer("market-agent.feedback")
    with tracer.start_as_current_span("user_feedback") as span:
        span.set_attribute("feedback.company", company)
        span.set_attribute("feedback.item_type", item_type)
        span.set_attribute("feedback.item_key", item_key)
        span.set_attribute("feedback.item_label", item_label)
        span.set_attribute("feedback.decision", decision)


def setup_arize() -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from arize.otel import GRPCSpanExporter

    space_id = os.environ["ARIZE_SPACE_KEY"]
    api_key = os.environ["ARIZE_API_KEY"]
    project_name = os.environ.get("ARIZE_MODEL_ID", "market-agent")

    exporter = SessionMappingExporter(
        GRPCSpanExporter(space_id=space_id, api_key=api_key)
    )

    provider = trace.get_tracer_provider()

    if isinstance(provider, TracerProvider):
        # ADK already set a real TracerProvider before we loaded.
        # Add our processors directly to it rather than trying to replace it.
        provider.add_span_processor(ArizeEnrichmentProcessor(project_name))
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        # No real provider yet (ProxyTracerProvider) — use register() to set one.
        from arize.otel import register
        register(
            space_id=space_id,
            api_key=api_key,
            project_name=project_name,
            span_processors=[
                ArizeEnrichmentProcessor(project_name),
                BatchSpanProcessor(exporter),
            ],
            batch=False,
        )
