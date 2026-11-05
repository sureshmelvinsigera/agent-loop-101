"""
Minimal Claude agent with tool use: the core skill behind this job.

Setup:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
Run:
    python agent_demo.py
    python agent_demo.py "What is 1234 * 5678, and what's the weather in NYC?"

The big idea (teach this to others!):
    An "agent" is just a loop:
      1. Send messages + tool definitions to the model.
      2. If the model replies with stop_reason == "tool_use", run the tool(s)
         yourself and send the results back as a "tool_result".
      3. Repeat until the model replies with stop_reason == "end_turn".
"""
import sys
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
MODEL = "claude-sonnet-5-5"

# ---- 1. Tool definitions: a name, a description, and a JSON Schema ----------
# The description is a prompt: the model decides when to call a tool from it.
TOOLS = [
    {
        "name": "calculate",
        "description": "Evaluate a basic arithmetic expression like '12 * (3 + 4)'.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
    {
        "name": "get_weather",
        "description": "Get the current weather for a city (fake data for the demo).",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
]


# ---- 2. Tool implementations: plain Python functions ------------------------
def calculate(expression: str) -> str:
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "Error: only basic arithmetic is allowed."
    return str(eval(expression, {"__builtins__": {}}))  # safe enough for a demo


_weather_calls: dict[str, int] = {}


def get_weather(city: str) -> str:
    # EXERCISE 2: the first call for each city fails on purpose, like a real outage.
    # Run it and watch whether the model retries, changes its approach, or gives up.
    _weather_calls[city] = _weather_calls.get(city, 0) + 1
    if _weather_calls[city] == 1:
        raise ConnectionError("weather service unavailable (HTTP 503)")
    return f"{city}: 58F, light rain"


IMPLEMENTATIONS = {"calculate": calculate, "get_weather": get_weather}


# ---- 3. The agent loop ------------------------------------------------------
def run_agent(user_prompt: str, max_turns: int = 10) -> str:
    messages = [{"role": "user", "content": user_prompt}]

    for turn in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )
        # Keep the assistant turn (including its tool_use blocks) in history.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Done: return the final text.
            return "".join(b.text for b in response.content if b.type == "text")

        # Run every tool the model asked for, then reply with the results.
        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"[turn {turn}] tool call: {block.name}({block.input})")
                is_error = False
                try:
                    output = IMPLEMENTATIONS[block.name](**block.input)
                except Exception as e:  # return errors to the model so it can recover
                    output = f"Error: {e}"
                    is_error = True
                    print(f"[turn {turn}] tool failed: {output}")
                result = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                }
                if is_error:
                    # Tells the model the tool FAILED, rather than "Error: ..." being the answer.
                    result["is_error"] = True
                results.append(result)
        messages.append({"role": "user", "content": results})

    return "Stopped: hit max_turns."


if __name__ == "__main__":
    prompt = (
            " ".join(sys.argv[1:])
            or "What's 1234 * 5678, and should I bring an umbrella in New York?"
    )
    print(run_agent(prompt))

# ---- Exercises (great teaching material too) --------------------------------
# 1. Add a third tool, e.g. search_notes(query), and watch the model pick it.
# 2. Break a tool on purpose (raise an exception) and see how the model recovers.
# 3. Add a system prompt via system="..." and see how behavior changes.
# 4. Stream the response with client.messages.stream(...) for live output.
# 5. Move the tools into an MCP server so any client can reuse them.