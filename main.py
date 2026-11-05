"""
Exercise 5: the agent loop, with its tools served by an MCP server.

Compare with main on the `main` branch: the loop is the same, but the tool
definitions and implementations moved to mcp_server.py. This file now
  1. starts the server and asks it which tools it has (list_tools),
  2. hands those definitions to Claude, and
  3. forwards each tool_use request to the server (call_tool).

Setup:
    uv add anthropic mcp
    export ANTHROPIC_API_KEY=sk-ant-...
Run:
    uv run main.py "What is 1234 * 5678, and what's the weather in NYC?"
"""
import asyncio
import sys

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from the environment
MODEL = "claude-sonnet-5-5"

SERVER = StdioServerParameters(command=sys.executable, args=["mcp_server.py"])


def to_anthropic_tool(tool) -> dict:
    """MCP tool definitions map almost one-to-one onto Claude's tool format."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.inputSchema,
    }


async def run_agent(user_prompt: str, max_turns: int = 10) -> str:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [to_anthropic_tool(t) for t in (await session.list_tools()).tools]

            messages = [{"role": "user", "content": user_prompt}]
            for turn in range(max_turns):
                response = await client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    tools=tools,
                    messages=messages,
                )
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason != "tool_use":
                    return "".join(b.text for b in response.content if b.type == "text")

                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"[turn {turn}] tool call: {block.name}({block.input})")
                        result = await session.call_tool(block.name, block.input)
                        text = "".join(c.text for c in result.content if c.type == "text")
                        entry = {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": text,
                        }
                        if result.isError:
                            entry["is_error"] = True
                        results.append(entry)
                messages.append({"role": "user", "content": results})

            return "Stopped: hit max_turns."


if __name__ == "__main__":
    prompt = (
        " ".join(sys.argv[1:])
        or "What's 1234 * 5678, and should I bring an umbrella in New York?"
    )
    print(asyncio.run(run_agent(prompt)))
