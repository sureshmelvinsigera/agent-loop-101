"""
Order-support agent: looks up orders and issues refunds.

Check it:
    uv run debug_challenge/check.py
Or ask it something directly:
    uv run debug_challenge/agent.py "What's the status of order A100?"
"""
import json
import sys

import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
MODEL = "claude-sonnet-5-5"

SYSTEM = (
    "You are a support agent for an online store. Use the tools to look up "
    "orders and issue refunds. Be brief and accurate."
)

# ---- Data ---------------------------------------------------------------------
ORDERS = {
    "A100": {"customer": "dana", "total": 80.00, "status": "shipped"},
    "A200": {"customer": "dana", "total": 120.00, "status": "processing"},
    "B300": {"customer": "lee", "total": 45.50, "status": "delivered"},
}
REFUNDS: list[dict] = []

# ---- Tool definitions ---------------------------------------------------------
TOOLS = [
    {
        "name": "lookup_order",
        "description": "Look up an order by its ID. Returns the customer, total in dollars, and status.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "refund_order",
        "description": "Refund an amount in dollars on an order. The amount cannot exceed the order total.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["id", "amount"],
        },
    },
]


# ---- Tool implementations -----------------------------------------------------
def lookup_order(args: dict) -> str:
    order_id = args["order_id"]
    order = ORDERS.get(order_id)
    if order is None:
        raise KeyError(f"no such order: {order_id}")
    return json.dumps({"order_id": order_id, **order})


def refund_order(args: dict) -> str:
    order_id = args["order_id"]
    amount = float(args["amount"])
    order = ORDERS[order_id]
    if amount > order["total"]:
        raise ValueError(f"refund {amount} exceeds order total {order['total']}")
    REFUNDS.append({"order_id": order_id, "amount": amount})
    return f"Refunded ${amount:.2f} on {order_id}"


IMPLEMENTATIONS = {"lookup_order": lookup_order, "refund_order": refund_order}


# ---- The agent loop -----------------------------------------------------------
def run_agent(user_prompt: str, max_turns: int = 10) -> str:
    messages = [{"role": "user", "content": user_prompt}]

    for turn in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        results = []
        for block in response.content:
            if block.type == "tool_use":
                try:
                    output = IMPLEMENTATIONS[block.name](block.input)
                except Exception:
                    output = ""
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    }
                )
                break
        messages.append({"role": "user", "content": results})

    return "Stopped: hit max_turns."


if __name__ == "__main__":
    print(run_agent(" ".join(sys.argv[1:]) or "What's the status of order A100?"))
