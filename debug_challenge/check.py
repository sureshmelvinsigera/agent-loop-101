"""
Acceptance checks for the order-support agent. These make real API calls.

    export ANTHROPIC_API_KEY=sk-ant-...
    uv run debug_challenge/check.py

Goal: get every check to PASS.
"""
import os
import sys

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("Set ANTHROPIC_API_KEY first: these checks call the real API.")

import agent  # debug_challenge/agent.py

calls: list[tuple[str, dict]] = []


def _record(name, fn):
    def wrapper(args):
        calls.append((name, dict(args)))
        return fn(args)

    return wrapper


for _name, _fn in list(agent.IMPLEMENTATIONS.items()):
    agent.IMPLEMENTATIONS[_name] = _record(_name, _fn)

DECLINE_WORDS = ["exceed", "cannot", "can't", "unable", "couldn't", "could not", "not able", "over the"]


def looked_up():
    return {a.get("order_id") for n, a in calls if n == "lookup_order"}


def check_status(answer):
    return [] if "shipped" in answer.lower() else ["answer does not say the order shipped"]


def check_two_orders(answer):
    failures = []
    if looked_up() != {"A100", "A200"}:
        failures.append(f"looked up {sorted(map(str, looked_up()))}, expected A100 and A200")
    if "A200" not in answer:
        failures.append("answer does not name A200 as the more expensive order")
    return failures


def check_refund_ok(answer):
    expected = [{"order_id": "A100", "amount": 20.0}]
    return [] if agent.REFUNDS == expected else [f"refunds in the system: {agent.REFUNDS}, expected {expected}"]


def check_refund_too_big(answer):
    failures = []
    if agent.REFUNDS:
        failures.append(f"a refund went through that should have been refused: {agent.REFUNDS}")
    if not any(w in answer.lower() for w in DECLINE_WORDS):
        failures.append("answer does not tell the customer the refund was declined")
    return failures


CASES = [
    ("order status", "What's the status of order A100?", check_status),
    ("two orders at once", "Which is more expensive, order A100 or order A200?", check_two_orders),
    ("valid refund", "Please refund $20 on order A100.", check_refund_ok),
    ("refund above the total", "Please refund $500 on order A100.", check_refund_too_big),
]


def main() -> int:
    passed = 0
    for name, prompt, check in CASES:
        calls.clear()
        agent.REFUNDS.clear()
        try:
            answer = agent.run_agent(prompt)
            failures = check(answer)
        except Exception as e:
            answer, failures = "", [f"crashed: {type(e).__name__}: {str(e)[:200]}"]
        passed += not failures
        print(f"{'PASS' if not failures else 'FAIL'}  {name}")
        for reason in failures:
            print(f"      - {reason}")
        if answer:
            print(f"      agent said: {answer[:160]!r}")
    print(f"\n{passed}/{len(CASES)} passed")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
