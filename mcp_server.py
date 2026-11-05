"""
Exercise 5: the same two tools, served over MCP so any MCP client can reuse them.

Run it on its own (it speaks MCP over stdio):
    uv run mcp_server.py
Normally the agent in main.py starts it for you.
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agent-loop-101-tools")


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a basic arithmetic expression like '12 * (3 + 4)'."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "Error: only basic arithmetic is allowed."
    return str(eval(expression, {"__builtins__": {}}))  # safe enough for a demo


@mcp.tool()
def get_weather(city: str) -> str:
    """Get the current weather for a city (fake data for the demo)."""
    return f"{city}: 58F, light rain"  # swap in a real API call here


if __name__ == "__main__":
    mcp.run()
