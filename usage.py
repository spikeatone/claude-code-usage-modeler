#!/usr/bin/env python3
"""Claude Code usage modeler - read local /usage history and project it forward.

Claude Code samples the `/usage` limit bars every ~5 minutes
and persists them to

    ~/Library/Application Support/Claude/plan-usage-history.json

as {"version":2, "samples":[{"t":<epoch ms>, "org":<uuid>,
                             "u":{"fh":<5h window %>, "sd":<7d window %>}}, ...]}

`fh` is the rolling five-hour window (percent consumed, 0-100); `sd` is the
seven-day window. Those are the same numbers `/usage` prints. There is no token
count and no reset timestamp in the file, so we infer both:

  * the 5-hour window rolls continuously, so its reset is "now + however long
    until the current burn unwinds" - we treat it as a 5h rolling budget and
    report time-to-reset as 5h from the oldest still-counting activity, which
    in practice we approximate from the window length.
  * the 7-day window resets on a fixed weekly anchor. We detect it empirically
    from the history: every sharp drop in `sd` is a reset, and the observed
    resets cluster on one weekday/time. We fit that anchor and roll it forward.

Everything here is read-only. It never writes the history file.

`load_usage()` returns the full model the panel needs; `main()` prints it as
JSON so the logic can be eyeballed from the shell:

    python3 usage.py
"""

import datetime
import glob
import json
import os
import sys

# Where Claude Code writes the sampled `/usage` history. The macOS location is
# the primary one; the others are cheap fallbacks so a slightly different setup
# still finds the file instead of dead-ending on "no data".
_CANDIDATES = [
    "~/Library/Application Support/Claude/plan-usage-history.json",   # macOS
    "~/.config/Claude/plan-usage-history.json",                       # Linux-ish
    "~/.claude/plan-usage-history.json",                             # fallback
]
if sys.platform.startswith("win"):
    _CANDIDATES.insert(0, os.path.join(
        os.environ.get("APPDATA", "~"), "Claude", "plan-usage-history.json"))


def find_history_path():
    """Return the first usage-history file that exists, or the macOS default
    path (so callers have something to show even when nothing is found yet)."""
    for cand in _CANDIDATES:
        p = os.path.expanduser(cand)
        if os.path.isfile(p):
            return p
    return os.path.expanduser(_CANDIDATES[0])


HISTORY_PATH = find_history_path()

# Sharp drops of at least this many points read as a window reset, not usage
# ticking down (usage only goes up within a window).
RESET_DROP = 15
# When measuring the current burn rate, look back at most this many hours so a
# quiet overnight stretch doesn't drag the rate toward zero.
BURN_LOOKBACK_H = 2.0
# ...but require at least this much span so a couple of samples a minute apart
# don't produce a wild slope. If the recent window is too short we widen it.
BURN_MIN_SPAN_H = 0.5

# A measured active-pace needs at least this much active time AND this many
# points of movement behind it before the page will extrapolate it over a
# whole week. Below either bar the number is shown but marked unreliable.
MIN_ACTIVE_H = 4.0
MIN_ACTIVE_GAIN = 3.0

FIVE_HOUR = 5.0
WEEK_DAYS = 7


def _read_samples(path=HISTORY_PATH):
    """Return sorted, cleaned samples or [] if the file is missing/unreadable."""
    try:
        with open(path) as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    out = []
    for s in raw.get("samples", []):
        t = s.get("t")
        u = s.get("u") or {}
        fh, sd = u.get("fh"), u.get("sd")
        if t is None or fh is None or sd is None:
            continue
        out.append({"t": int(t), "fh": float(fh), "sd": float(sd),
                    "org": s.get("org")})
    out.sort(key=lambda x: x["t"])
    return out


def _burn_rate(samples, key, now_ms):
    """Points-per-hour for `key` over the recent window, clamped at >= 0.

    Usage climbs within a window, so a negative slope means a reset landed in
    the lookback; in that case we measure only the tail after the last reset.
    Returns 0.0 only when the burn is genuinely unknowable (too little data /
    span too short / only one post-reset sample) - callers treat 0.0 as idle.
    """
    if len(samples) < 2:
        return 0.0
    span_ms = BURN_LOOKBACK_H * 3600_000
    recent = [s for s in samples if now_ms - s["t"] <= span_ms]
    # Widen (by pulling in older samples) until the span is usable, or we run
    # out of history. Track whether we actually reached the minimum span.
    i = len(samples) - 1
    min_span_ms = BURN_MIN_SPAN_H * 3600_000
    while (len(recent) < 2 or
           recent[-1]["t"] - recent[0]["t"] < min_span_ms):
        i -= 1
        if i < 0:
            break
        recent = samples[i:]
    # If we still can't span the minimum, the rate is unknowable - don't invent
    # a wild slope from two samples a few minutes apart.
    if len(recent) < 2 or recent[-1]["t"] - recent[0]["t"] < min_span_ms:
        return 0.0
    # If a reset sits inside the window, keep only the tail after the last drop.
    start = 0
    for j in range(1, len(recent)):
        if recent[j][key] - recent[j - 1][key] <= -RESET_DROP:
            start = j
    tail = recent[start:]
    # The post-reset tail may be too short to measure. Rather than reporting a
    # false 0.0 ("idle -> clear") right after a reset, fall back to the burn
    # since the reset across the *whole* history tail we have.
    if len(tail) >= 2 and tail[-1]["t"] - tail[0]["t"] >= min_span_ms:
        recent = tail
    elif start > 0:
        # Reset happened but the tail is too short: widen the tail using all
        # samples after that reset from the full history, not just the window.
        reset_t = recent[start]["t"]
        wide_tail = [s for s in samples if s["t"] >= reset_t]
        if len(wide_tail) >= 2 and wide_tail[-1]["t"] - wide_tail[0]["t"] >= min_span_ms:
            recent = wide_tail
        else:
            return 0.0            # genuinely too little post-reset data
    dt_h = (recent[-1]["t"] - recent[0]["t"]) / 3600_000
    if dt_h <= 0:
        return 0.0
    rate = (recent[-1][key] - recent[0][key]) / dt_h
    return max(0.0, rate)


def _weekly_resets(samples):
    """Reset instants (ms), bracketed to survive sampling gaps.

    A reset is a sharp drop in `sd`. The naive timestamp is the first sample
    AFTER the drop - but sampling stops whenever Claude Code isn't running, so
    a machine asleep overnight reports the reset hours late. (Real case: the
    last sample before a reset was Tue 17:49 at 100%, the next was Wed 09:18
    at 0% - a 15.5h gap that made a Tue 21:00 reset look like Wed 09:18 and
    dragged the whole anchor onto the wrong weekday.)

    Each reset is returned as {"after": <last sample before>, "before": <first
    sample after>}: the true instant lies in that bracket. `_weekly_anchor`
    picks the point in the bracket that fits the observed weekly cadence.
    """
    out = []
    for a, b in zip(samples, samples[1:]):
        if a["sd"] - b["sd"] >= RESET_DROP:
            out.append({"after": a["t"], "before": b["t"]})
    return out


def _reset_times(resets):
    """Just the bracket end (first observed sample after each reset)."""
    return [r["before"] for r in resets]


def _weekly_anchor(resets):
    """Infer the weekly reset instant, tolerant of gaps in the samples.

    Anchoring naively to the newest reset's post-drop timestamp is wrong when
    that sample landed after a sampling gap. So: take the newest reset whose
    bracket is tight (the machine was awake across it) and roll it forward in
    whole weeks to the newest reset's bracket. If every bracket is loose, fall
    back to the midpoint of the newest one - still better than its late edge.
    """
    if not resets:
        return None
    newest = resets[-1]
    week_ms = WEEK_DAYS * 24 * 3600_000

    # A bracket under ~35 min pins the instant well (sampling is ~5-15 min).
    tight = [r for r in resets if r["before"] - r["after"] <= 35 * 60_000]
    if tight:
        ref = tight[-1]
        # Midpoint of a tight bracket is within minutes of the true instant.
        instant = (ref["after"] + ref["before"]) // 2
        # Roll forward in whole weeks until it lands in/after the newest reset's
        # bracket, so the anchor reflects the most recent cycle.
        while instant + week_ms <= newest["before"]:
            instant += week_ms
    else:
        instant = (newest["after"] + newest["before"]) // 2

    ref_dt = datetime.datetime.fromtimestamp(instant / 1000)
    return {"weekday": ref_dt.weekday(), "hour": ref_dt.hour,
            "minute": ref_dt.minute, "last_reset_ms": instant}


def _next_weekly_reset(anchor, now_dt):
    """Next weekly reset at or after `now_dt`.

    Roll forward from the actual last-reset instant in whole-week steps. Working
    from the real epoch instant (not a replayed wall-clock time) keeps the reset
    on a fixed cadence across DST transitions instead of drifting an hour.
    """
    if not anchor or not anchor.get("last_reset_ms"):
        return None
    last = datetime.datetime.fromtimestamp(anchor["last_reset_ms"] / 1000)
    week = datetime.timedelta(days=WEEK_DAYS)
    candidate = last
    while candidate <= now_dt:
        candidate += week
    return candidate


def _active_rate(samples, resets, now_ms):
    """Measured pace while actually working, from the CURRENT week only.

    By request, past weeks feed nothing: each week is unique, so the tool
    ships neutral facts about this one - sd points gained per hour of active
    time (active = the 5h window shows live usage, fh > 2) - and the page's
    sliders turn that into a plan. Sampling gaps over 30 min read as idle.
    """
    start = resets[-1]["before"] if resets else now_ms - 7 * 24 * 3600_000
    week = [s for s in samples if s["t"] >= start]
    gain = 0.0
    hours = 0.0
    for a, b in zip(week, week[1:]):
        gap_h = (b["t"] - a["t"]) / 3600_000
        if gap_h > 0.5:
            continue
        if a["fh"] > 2 or b["fh"] > 2:
            hours += gap_h
            gain += max(0.0, b["sd"] - a["sd"])
    # A rate measured over a sliver of active time is noise, not a pace: right
    # after a reset one busy hour would otherwise be extrapolated across the
    # whole week (seen live: 2.1 active hours read as 3.9 pts/hr -> a 216%
    # projection from 0%). Report the measurement either way, but flag whether
    # it is solid enough to drive a projection; the page falls back to a
    # neutral plan-it-yourself state when it isn't.
    if hours <= 0:
        return None
    rate = gain / hours
    return {"rate_per_h": round(rate, 3),
            "active_hours": round(hours, 1),
            "reliable": hours >= MIN_ACTIVE_H and gain >= MIN_ACTIVE_GAIN}


def _fh_window_start(samples, now_ms):
    """Approximate start of the live 5-hour window, or None if unknowable.

    The fh series steps: it climbs while a session block is active and drops
    when the block's window expires. The window opened at the last idle->climb
    transition (or right after the last drop). Sampling is ~5min so this is
    approximate - callers should present it as "~" - but it beats the old
    behavior of always projecting a full fresh 5 hours.
    """
    horizon = [s for s in samples if now_ms - s["t"] <= FIVE_HOUR * 3600_000]
    if len(horizon) < 2 or horizon[-1]["fh"] <= 2:
        return None                      # idle now, or nothing to see
    start = None
    for prev, cur in zip(horizon, horizon[1:]):
        if prev["fh"] - cur["fh"] >= RESET_DROP:
            start = cur["t"]             # window re-opened at the drop
        elif prev["fh"] <= 2 < cur["fh"]:
            start = prev["t"]            # climbed out of idle
    return start


def _project(pct, rate_per_h, hours_to_reset):
    """Given current %, burn rate (pts/h) and hours until the window resets,
    return the projection: hours until 100%, projected % at reset, verdict."""
    remaining = max(0.0, 100.0 - pct)
    if rate_per_h <= 0.0001:
        hours_to_full = None            # not burning -> never hits the cap
        pct_at_reset = pct
    else:
        hours_to_full = remaining / rate_per_h
        if hours_to_reset is None:
            pct_at_reset = None
        else:
            # Raw projection can exceed 100 - that's the signal we're modeling.
            # Keep the true projected value; the UI decides how to show >100.
            pct_at_reset = pct + rate_per_h * hours_to_reset

    # Verdict: will we hit 100% before the window resets?
    if hours_to_reset is None:
        verdict = "unknown"
    elif hours_to_full is None:
        verdict = "clear"               # idle / negligible burn
    elif hours_to_full >= hours_to_reset * 1.15:
        verdict = "clear"               # comfortably resets before running dry
    elif hours_to_full >= hours_to_reset:
        verdict = "tight"               # lands close - watch it
    else:
        verdict = "over"                # will run out before reset
    pct_at_reset_capped = (min(100.0, pct_at_reset)
                           if pct_at_reset is not None else None)
    return {"hours_to_full": hours_to_full, "pct_at_reset": pct_at_reset,
            "pct_at_reset_capped": pct_at_reset_capped,
            "verdict": verdict, "remaining_pct": remaining}


def load_usage(path=None, now_ms=None):
    """Build the full usage model for the panel. Read-only.

    Returns a dict with current state, burn rates, reset timing and forward
    projections for both windows, plus a compact history series for the chart.
    `path` defaults to auto-detection (re-checked each call, so the file can
    appear after Claude Code first records usage). `now_ms` can be pinned for
    tests; otherwise the newest sample is "now".
    """
    if path is None:
        path = find_history_path()
    samples = _read_samples(path)
    if not samples:
        # Not an error - most likely first run. Hand the UI what it needs to
        # onboard: the paths we looked in and whether any file exists at all.
        checked = [os.path.expanduser(c) for c in _CANDIDATES]
        found = next((p for p in checked if os.path.isfile(p)), None)
        return {
            "available": False,
            "primary_path": os.path.expanduser(_CANDIDATES[0]),
            "checked_paths": checked,
            "file_exists": found is not None,
            "reason": ("found %s but it has no samples yet" % found) if found
                      else "no usage history file found yet",
        }

    latest = samples[-1]
    # Wall-clock "now", not the newest sample: sampling stops when Claude Code
    # isn't running (this history has 40+ gaps over an hour), and presenting
    # day-old percentages as current was one of the tool's real inaccuracies.
    # The staleness is measured and surfaced instead of hidden. `now_ms` can
    # still be pinned for tests.
    if now_ms is None:
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        now_ms = max(now_ms, latest["t"])     # tolerate clock skew in the file
    now_dt = datetime.datetime.fromtimestamp(now_ms / 1000)
    data_age_min = (now_ms - latest["t"]) / 60_000

    # Burn rates are measured at the newest sample (measuring at a stale "now"
    # would dilute the slope with empty time).
    fh_rate = _burn_rate(samples, "fh", latest["t"])
    sd_rate = _burn_rate(samples, "sd", latest["t"])

    # 5-hour window: fh steps, it doesn't roll smoothly - it climbs during a
    # session block and drops ~5h after the block began. Estimate the live
    # window's start so the projection horizon is the time actually left, not
    # a fresh 5 hours every render.
    fh_start = _fh_window_start(samples, now_ms)
    if fh_start is not None:
        fh_resets_by = fh_start + int(FIVE_HOUR * 3600_000)
        fh_horizon = max(0.0, (fh_resets_by - now_ms) / 3600_000)
    else:
        fh_resets_by = None
        fh_horizon = FIVE_HOUR            # unknown start: ceiling, labeled "<=5h"
    five_h = _project(latest["fh"], fh_rate, fh_horizon)

    # 7-day window: anchored to the most recent observed reset.
    resets = _weekly_resets(samples)
    anchor = _weekly_anchor(resets)
    next_reset_dt = _next_weekly_reset(anchor, now_dt)
    hours_to_weekly = ((next_reset_dt - now_dt).total_seconds() / 3600
                       if next_reset_dt else None)

    # By request, no inference from past weeks: the projection is a PLAN.
    # The server ships neutral current-state facts - pct, time to reset, the
    # recent burst rate, and this week's measured pace while active - and the
    # page's sliders (hours/day x model x effort) turn them into a projection.
    # The server-side verdict is simply "if the current burst continues".
    active = _active_rate(samples, resets, now_ms)
    seven_d = _project(latest["sd"], sd_rate, hours_to_weekly)

    # Compact history for the sparkline/chart: last ~72h, thinned to <= 240 pts.
    horizon = now_ms - 72 * 3600_000
    series = [s for s in samples if s["t"] >= horizon]
    if len(series) > 240:
        step = len(series) // 240 + 1
        series = series[::step]
    hist = [{"t": s["t"], "fh": s["fh"], "sd": s["sd"]} for s in series]

    return {
        "available": True,
        "path": path,
        "now_ms": now_ms,
        "latest_sample_ms": latest["t"],
        "data_age_min": round(data_age_min, 1),
        "org": latest.get("org"),
        "sample_count": len(samples),
        "history_from_ms": samples[0]["t"],
        "five_hour": {
            "pct": latest["fh"], "rate_per_h": round(fh_rate, 2),
            "window_h": FIVE_HOUR,
            "window_start_ms": fh_start,
            "resets_by_ms": fh_resets_by,
            "horizon_h": round(fh_horizon, 2),
            **five_h,
        },
        "seven_day": {
            "pct": latest["sd"],
            "rate_per_h": round(sd_rate, 3),          # burst: "if you keep this up"
            "active": active,      # this week's pace while active, or None
            "next_reset_ms": int(next_reset_dt.timestamp() * 1000) if next_reset_dt else None,
            "hours_to_reset": round(hours_to_weekly, 2) if hours_to_weekly is not None else None,
            "anchor": anchor, **seven_d,
        },
        "history": hist,
    }


def scan_token_totals(window_hours=None, now_ms=None):
    """Optional detail: sum token usage from session transcripts.

    Not needed for the percentage model (that comes from plan-usage-history),
    but gives a token-level breakdown by model over a recent window. Streams
    the JSONL transcripts; skips anything malformed. Returns {} on any trouble.
    """
    base = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(base):
        return {}
    cutoff = None
    if window_hours is not None:
        ref = now_ms or int(datetime.datetime.now().timestamp() * 1000)
        cutoff = ref - window_hours * 3600_000
    by_model = {}
    paths = glob.glob(os.path.join(base, "*", "*.jsonl"))
    paths += glob.glob(os.path.join(base, "*", "*", "subagents", "*.jsonl"))
    for p in paths:
        try:
            with open(p) as handle:
                for line in handle:
                    line = line.strip()
                    if not line or '"usage"' not in line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get("type") != "assistant":
                        continue
                    msg = row.get("message") or {}
                    usage = msg.get("usage")
                    if not usage:
                        continue
                    if cutoff is not None:
                        ts = row.get("timestamp")
                        if not ts:
                            continue
                        try:
                            tms = datetime.datetime.fromisoformat(
                                ts.replace("Z", "+00:00")).timestamp() * 1000
                        except ValueError:
                            continue
                        if tms < cutoff:
                            continue
                    model = msg.get("model") or "unknown"
                    agg = by_model.setdefault(model, {
                        "input": 0, "output": 0, "cache_read": 0, "cache_create": 0})
                    agg["input"] += usage.get("input_tokens", 0) or 0
                    agg["output"] += usage.get("output_tokens", 0) or 0
                    agg["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
                    agg["cache_create"] += usage.get("cache_creation_input_tokens", 0) or 0
        except OSError:
            continue
    return by_model


def main():
    import argparse
    parser = argparse.ArgumentParser(description="print the usage model as JSON")
    parser.add_argument("--tokens", action="store_true",
                        help="also scan transcripts for a token breakdown (slow)")
    args = parser.parse_args()
    model = load_usage()
    if args.tokens and model.get("available"):
        model["tokens_7d"] = scan_token_totals(window_hours=24 * 7)
    print(json.dumps(model, indent=2))


if __name__ == "__main__":
    main()
