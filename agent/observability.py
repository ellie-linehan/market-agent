import os
from arize.otel import register
from opentelemetry import trace

_tracer: trace.Tracer | None = None


def setup_arize() -> None:
    """Register Arize as the OTLP trace exporter."""
    register(
        space_id=os.environ["ARIZE_SPACE_KEY"],
        api_key=os.environ["ARIZE_API_KEY"],
        project_name=os.environ.get("ARIZE_MODEL_ID", "market-agent"),
    )
    global _tracer
    _tracer = trace.get_tracer("market-agent")


def get_tracer() -> trace.Tracer:
    if _tracer is None:
        raise RuntimeError("Call setup_arize() before get_tracer()")
    return _tracer
