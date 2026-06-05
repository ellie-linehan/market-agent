"""Renders the agent graph to a PNG and opens it."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv(override=True)

from google.adk.cli.agent_graph import get_agent_graph
from app.agent import root_agent


async def main():
    png_bytes = await get_agent_graph(root_agent, [], image=True, dark_mode=False)
    path = "agent_graph.png"
    with open(path, "wb") as f:
        f.write(png_bytes)
    print(f"Graph saved to: {path}")
    os.startfile(path)


asyncio.run(main())
