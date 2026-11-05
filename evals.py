"""
A tiny eval harness for agent-loop-101.

Each case is a prompt plus two kinds of checks:
  1. Which tools did the agent call? (the path)
  2. Does the final answer contain what we expect? (the result)

Run it (makes real API calls, so it needs a key):
    export ANTHROPIC_API_KEY=sk-ant-...
    uv run evals.py

Then change something (the model, a tool description, add a system prompt)
and run it again to compare scores.
"""
import os
import sys

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("Set ANTHROPIC_API_KEY first: these evals call the real API.")

import main  # the agent from main.py

CASES = [
    {
        "name": "math goes through the calculator",
        "prompt": "What is 1234 * 5678?",
        "expect_tools": {"calculate"},
        "answer_has": ["7006652"],
    },
    {
        "name": "weather goes through the weather tool",
        "prompt": "What's the weather in NYC?",
        "expect_tools": {"get_weather"},
        "answer_has": ["58"],
    },
    {
        "name": "no tool needed for general knowledge",
        "prompt": "What is the capital of France?",
        "expect_tools": set(),
        "answer_has": ["Paris"],
    },
    {
        "name": "uses both tools when asked for both",
        "prompt": "What is 1234 * 5678, and what's the weather in NYC?",
        "expect_tools": {"calculate", "get_weather"},
        "answer_has": ["7006652", "58"],
    },
]

# Record every tool call without touching main.py: wrap each implementation.
calls: list[str] = []


def _record(name, fn):
    def wrapper(**kwargs):
        calls.append(name)
        return fn(**kwargs)

    return wrapper


for _name, _fn in list(main.IMPLEMENTATIONS.items()):
    main.IMPLEMENTATIONS[_name] = _record(_name, _fn)


def grade(case, answer: str) -> list[str]:
    """Return a list of failure reasons (empty list = pass)."""
    failures = []
    used = set(calls)
    if used != case["expect_tools"]:
        failures.append(f"tools called {sorted(used)}, expected {sorted(case['expect_tools'])}")
    normalized = answer.replace(",", "")  # so "7,006,652" matches "7006652"
    for needle in case["answer_has"]:
        if needle not in normalized:
            failures.append(f"answer is missing {needle!r}")
    return failures


def run_evals(cases=CASES) -> tuple[int, int]:
    passed = 0
    for case in cases:
        calls.clear()
        try:
            answer = main.run_agent(case["prompt"])
            failures = grade(case, answer)
        except Exception as e:  # a crash is a failed case, not a crashed eval run
            failures = [f"crashed: {e}"]
        passed += not failures
        print(f"{'PASS' if not failures else 'FAIL'}  {case['name']}")
        for reason in failures:
            print(f"      - {reason}")
    print(f"\n{passed}/{len(cases)} passed")
    return passed, len(cases)


if __name__ == "__main__":
    passed, total = run_evals()
    sys.exit(0 if passed == total else 1)
