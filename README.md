# Claude Code Usage Modeler

A tiny local tool that shows how your Claude Code usage is tracking against your
limits — and whether you can push more sessions (or turn on Ultracode) before a
window resets, or need to pull back so you don't run over.

It reads the usage history Claude Code already keeps on your own machine (the
same 5‑hour and 7‑day percentages the `/usage` command shows), measures your
recent burn rate, works out when each window resets, and projects forward.

**It never leaves your machine.** There's no account login and nothing to paste
— it reads a local file Claude Code writes, binds to `localhost` only, and never
writes anything back to your usage data.

<!-- Add a screenshot here if you like: ![screenshot](screenshot.png) -->

## Requirements

- **Python 3** (any recent 3.x — it's already on macOS). No packages to install;
  standard library only.
- **Claude Code**, installed and run at least once. See below.

## Run it

```bash
python3 serve.py
```

That starts a local server and opens `http://127.0.0.1:8787/` in your browser.

First time? The page walks you through it: run `/usage` inside any Claude Code
session once so Claude Code starts recording your usage, and the dashboard loads
itself the moment the data appears. (You only do that once; it keeps updating
after.)

Options:

```bash
python3 serve.py --port 9000     # use a different port
python3 serve.py --no-open       # don't launch a browser
```

## What it shows

- **A verdict** — *Room to push / Hold steady / Pull back* — from whichever
  window is closest to running out.
- **Two gauges**: the rolling 5‑hour session window and the 7‑day weekly window,
  each with how much you've used, your current burn rate, when it resets, and
  where you're projected to land by then.
- **A 72‑hour chart** of both windows.
- **"Model a change"** what‑if controls: how many hours a day you plan to keep
  working, which **model** you'll run (Fable / Opus / Sonnet), and at what
  **effort** (Low → Medium → High → Extra → Max → Ultracode). Effective burn is
  model × effort, and the weekly projection updates live. Your choices persist
  across sessions.
- An **Ultracode** read‑out on top of that: Ultracode isn't a plan upgrade, it's
  multi‑agent orchestration that burns roughly 2.5× faster. The tool tells you
  whether your weekly budget can absorb it before the reset — on whichever model
  you've selected.

### About the multipliers

Everything is relative to a baseline of **1.0 = Opus at Extra effort** (`xhigh`,
Claude Code's default) — the configuration most measured burn history is
recorded on.

**Model factors come from Anthropic's published API pricing** (per million
tokens, input/output): Fable 5 at $10/$50, Opus 5 and Opus 4.8 at $5/$25, and
Sonnet 5 at $3/$15. The input and output ratios agree exactly, so the factors are
unambiguous — Fable is **2.0×** Opus and Sonnet is **0.6×**.

**Effort factors are estimates.** Effort changes how many tokens a task consumes,
not the per‑token price, and Anthropic publishes no cost figures for effort
levels — so these are calibrated by observation rather than derived from a price
list. They live in one place (`EFFORTS` near the top of the page script in
`usage_page.py`) and are a one‑line change each if your own usage suggests
different ratios.

## Where the data comes from

Claude Code samples your `/usage` limits every ~5 minutes to a local file. The
tool looks for it here (first match wins):

- macOS: `~/Library/Application Support/Claude/plan-usage-history.json`
- Linux: `~/.config/Claude/plan-usage-history.json`
- Fallback: `~/.claude/plan-usage-history.json`

The file holds only the two percentages and a timestamp per sample — no message
contents. If yours lives somewhere else, the onboarding screen tells you which
paths were checked.

## How the projection works (so you can trust the numbers)

- **The weekly projection** is your *week‑to‑date pace* (usage so far ÷ hours
  since your last reset), which already contains your real mix of work, idle
  and sleep. Backtesting shows extrapolating the current burst runs hot; the
  burst rate is still shown as a secondary "if you keep this up" line.
- **The range, not a point.** The tool backtests its own projector against your
  completed weeks and shows the projection as a range (median error by
  time‑remaining — typically wide early in the week, tight near the reset).
  The verdict judges the range: "over" only when even the optimistic edge busts.
- **The weekly reset** is anchored to your *most recent* observed reset and
  rolled forward in 7‑day steps — so if your account's reset day ever moves,
  the tool follows it on the next reset.
- **The 5‑hour window** estimates when your current session window actually
  opened (it steps, it doesn't roll smoothly), so "time to reset" is the time
  you really have left — approximate, and labeled as such.
- **Staleness is surfaced.** Sampling stops when Claude Code isn't running;
  if the newest sample is old you get a banner, not silently stale numbers.

The math lives in `usage.py`; `test_usage.py` covers the edge cases (resets,
short histories, boundaries). Run the tests with:

```bash
python3 test_usage.py
```

## Files

| File | What it is |
|------|------------|
| `serve.py` | The local server (two read‑only routes). Run this. |
| `usage.py` | Reads the history file and builds the projection model. |
| `usage_page.py` | The dashboard page (HTML + a small client app). |
| `test_usage.py` | Edge‑case tests for the projection math. |

## Privacy

Everything runs locally. The server binds to `127.0.0.1` (your machine only),
reads one local file, and writes nothing. No network calls, no telemetry, no
account.
