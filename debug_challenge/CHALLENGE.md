# Debug the broken agent (timed practice)

`agent.py` is an order-support agent. It looks up orders and issues refunds.
It is broken. Make `check.py` print 4/4 PASS.

## Rules (they mirror the real round)
- 55 minutes. Set a timer.
- Python only. Claude Code is allowed: use a smaller model than your top one, in manual (approve-each-edit) mode.
- Talk out loud the whole time: what you suspect, what you will check, what you saw.
- No peeking at the answer key until the timer ends.

## Setup
    export ANTHROPIC_API_KEY=sk-ant-...
    uv run debug_challenge/check.py

## What users are reporting
- "Asking for an order status just errors out."
- "When I compare two orders it falls over or only knows about one."
- "Refunds say they worked but nothing shows up."
- "It told me a refund went through when it was more than my order."

## Suggested plan
- 0-10 min: run the checks, read agent.py top to bottom, say how the loop works before touching anything.
- 10-40 min: fix one failure at a time. Re-run after every change.
- 40-50 min: all green? Add one test of your own for a case the checks miss.
- 50-55 min: summarize the root causes and what you would monitor in production.
