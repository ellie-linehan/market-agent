"""Self-reflection agent: introspects the agent's OWN operational data at
runtime through the Phoenix MCP server (the Arize-track integration).

The Phoenix MCP server (@arizeai/phoenix-mcp, via npx) exposes tools over
traces, spans, sessions, projects, datasets, experiments, and annotations.
We attach it to an ADK agent so it can answer "how is this agent performing
and what has it learned?" from real telemetry — not from guesses.
"""
import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

from app.agent import _model


def phoenix_configured() -> bool:
    return bool(
        os.environ.get("PHOENIX_API_KEY")
        and os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    )


def build_insights_agent() -> Agent:
    """Construct the insights agent wired to the Phoenix MCP server.

    Only call when phoenix_configured() — it spawns the MCP server via npx.
    """
    phoenix_tools = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=[
                    "-y",
                    "@arizeai/phoenix-mcp@latest",
                    "--baseUrl",
                    os.environ["PHOENIX_COLLECTOR_ENDPOINT"],
                    "--apiKey",
                    os.environ["PHOENIX_API_KEY"],
                ],
            ),
            # npx cold start + Phoenix handshake easily exceeds the 5s default,
            # which surfaced as intermittent "Failed to create MCP session".
            timeout=60.0,
        ),
    )
    project = os.environ.get("PHOENIX_PROJECT_NAME", "market-agent")
    return Agent(
        name="insights_agent",
        model=_model,
        instruction=f"""You are the self-reflection layer of a market-intelligence agent.

You have tools, via the Phoenix MCP server, to introspect this agent's OWN
operational data in the Phoenix project "{project}". Always call the tools by
their EXACT names (they use hyphens). The ones you need:
- list-projects            → find the "{project}" project and its id
- list-traces              → traces in a project (each analysis is a trace)
- get-trace / get-spans    → spans within a trace (LLM calls, tool calls)
- list-sessions / get-session
- get-span-annotations     → annotations on spans
Do NOT invent tool names or add prefixes; use the names above verbatim.

The agent's runs produce traces in "{project}"; keep/dismiss feedback is
recorded as user_feedback spans (attributes feedback.decision and
feedback.score, where keep=1 and dismiss=0).

When asked how the agent is doing or what it has learned, USE these tools to
pull real traces/spans, then answer concretely: how many analyses ran,
kept-vs-dismissed signal, latency or errors, and what it implies for improving
the agent. Ground every number in data you actually retrieved — never invent
figures. If a tool returns nothing, say so.""",
        tools=[phoenix_tools],
    )
