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
    """Timestamps (ms) where the 7-day window dropped sharply = a weekly reset."""
    resets = []
    for a, b in zip(samples, samples[1:]):
        if a["sd"] - b["sd"] >= RESET_DROP:
            resets.append(b["t"])
    return resets


def _weekly_anchor(resets):
    """Anchor the weekly cadence to the *most recent* observed reset.

    An earlier version voted for the dominant weekday across recent resets.
    That backfired in practice: when Anthropic moved this account's reset from
    Tue ~22:00 to Wed ~09:18 (observed 2026-08-19), the vote kept projecting
    Tuesdays - ~35h off. The newest reset is simply the truth; history adds
    nothing once the anchor moves.
    """
    if not resets:
        return None
    ref = datetime.datetime.fromtimestamp(resets[-1] / 1000)
    return {"weekday": ref.weekday(), "hour": ref.hour, "minute": ref.minute,
            "last_reset_ms": resets[-1]}


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


def _wtd_rate(samples, resets, now_ms):
    """Week-to-date pace: pts/hour averaged since the last weekly reset.

    Backtesting this history showed the 2h-slope projector runs ~+9pts hot
    (it extrapolates the current burst around the clock), while WTD pace is
    unbiased - it already contains the real mix of work, idle and sleep. It is
    the central projector; the burst slope stays as the "if you keep this up"
    secondary read.
    """
    if not resets:
        return None
    since = [s for s in samples if s["t"] >= resets[-1]]
    if not since:
        return None
    elapsed_h = (now_ms - resets[-1]) / 3600_000
    if elapsed_h < 6:
        return None                      # too early in the window to average
    return since[-1]["sd"] / elapsed_h


def _calibrate_band(samples, resets):
    """Projection uncertainty, learned from this user's own completed windows.

    For every checkpoint inside each completed weekly window, compute the
    week-to-date projector's SIGNED error (projection - actual end) and keep
    the p20/p80 quantiles, bucketed by hours-remaining. Signed quantiles beat
    a symmetric +/- band twice over: the error is skewed (early-week the
    projector runs hot, mid-week it runs low), so the asymmetric interval is
    both recentered and 15-60% narrower for the same confidence.
    """
    buckets = {"96": [], "48": [], "24": [], "0": []}
    for w in range(len(resets) - 1):
        a, b = resets[w], resets[w + 1]
        window = [s for s in samples if a <= s["t"] < b]
        if not window:
            continue
        end_pct = window[-1]["sd"]
        for s_ in window[::3]:            # thin 3x; precision isn't needed here
            elapsed = (s_["t"] - a) / 3600_000
            rem = (b - s_["t"]) / 3600_000
            if elapsed < 12 or rem < 1:
                continue
            err = (s_["sd"] + s_["sd"] / elapsed * rem) - end_pct
            key = "96" if rem >= 96 else "48" if rem >= 48 else \
                  "24" if rem >= 24 else "0"
            buckets[key].append(err)
    out = {}
    for key, errs in buckets.items():
        if len(errs) >= 10:               # too few checkpoints = no calibration
            errs.sort()
            lo = errs[min(len(errs) - 1, int(len(errs) * 0.2))]
            hi = errs[min(len(errs) - 1, int(len(errs) * 0.8))]
            out[key] = {"lo": round(lo, 1), "hi": round(hi, 1)}
    return out or None


def _band_for(band, hours_to_reset):
    """The signed-error quantiles {lo, hi} for the current hours-to-reset."""
    if not band or hours_to_reset is None:
        return None
    key = "96" if hours_to_reset >= 96 else "48" if hours_to_reset >= 48 else \
          "24" if hours_to_reset >= 24 else "0"
    # Fall back to the nearest populated bucket.
    for k in (key, "24", "48", "96", "0"):
        if k in band:
            return band[k]
    return None


def _max_gain_over(samples, resets, dur_h):
    """The most this user has EVER burned (sd points) inside any stretch of
    `dur_h` hours within a single weekly window. A physics cap on projections:
    the high end of the range can't exceed current + this (nobody projects a
    burn you've never once approached). Measured within windows so a reset
    drop never fakes a gain."""
    best = 0.0
    if not samples:
        return best
    # Segment boundaries: history start, each reset, history end - the stretch
    # before the first reset is a valid within-window run too.
    bounds = [samples[0]["t"]] + list(resets) + [samples[-1]["t"] + 1]
    for w in range(len(bounds) - 1):
        a, b = bounds[w], bounds[w + 1]
        pts = [s for s in samples if a <= s["t"] < b]
        j = 0
        for i in range(len(pts)):
            while pts[i]["t"] - pts[j]["t"] > dur_h * 3600_000:
                j += 1
            window_min = min(p["sd"] for p in pts[j:i + 1])
            best = max(best, pts[i]["sd"] - window_min)
    return best


def _final_stretch_gains(samples, resets, rem_h):
    """How many sd points each completed week added in its FINAL `rem_h` hours.

    The most legible answer to "is 66% with 2 days left actually tight?":
    replay your own past final-stretches from today's number. A verdict that
    can say "1 of your 3 past finishes would cap out from here" explains
    itself; a bare pill doesn't.
    """
    if rem_h is None or rem_h <= 0:
        return []
    gains = []
    for w in range(len(resets) - 1):
        a, b = resets[w], resets[w + 1]
        pts = [s for s in samples if a <= s["t"] < b]
        if len(pts) < 10:
            continue
        cutoff = b - rem_h * 3600_000
        before = [p["sd"] for p in pts if p["t"] <= cutoff]
        if not before:
            continue                      # window shorter than the stretch
        gains.append(round(pts[-1]["sd"] - before[-1], 1))
    return gains


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

    # Central projector: week-to-date pace (unbiased on backtest), with an
    # uncertainty band calibrated from this user's own completed windows.
    # The burst slope (sd_rate) stays available as "if you keep this up".
    wtd = _wtd_rate(samples, resets, now_ms)
    band_all = _calibrate_band(samples, resets)
    band = _band_for(band_all, hours_to_weekly)
    central_rate = wtd if wtd is not None else sd_rate
    seven_d = _project(latest["sd"], central_rate, hours_to_weekly)
    # The interval, tightened three ways beyond a naive +/- band:
    #   1. asymmetric: actual = projection - err, so the interval is
    #      [proj - err_hi, proj - err_lo] - recentered for the projector's
    #      bucket-specific bias, not just widened around it.
    #   2. floored at the current pct (usage never goes down within a window).
    #   3. capped at current + the most ever burned in the remaining hours
    #      (x1.1 headroom) - a projection can't exceed a burn you've never
    #      once approached.
    max_gain = (_max_gain_over(samples, resets, hours_to_weekly)
                if resets and hours_to_weekly else None)
    proj_low = proj_high = None
    if seven_d["pct_at_reset"] is not None and band is not None:
        proj_low = max(latest["sd"], seven_d["pct_at_reset"] - band["hi"])
        proj_high = seven_d["pct_at_reset"] - band["lo"]
        if max_gain is not None:
            proj_high = min(proj_high, latest["sd"] + max_gain * 1.1)
        proj_high = max(proj_high, proj_low + 5)   # never feign pinpoint accuracy
        if proj_low >= 100:
            seven_d["verdict"] = "over"
        elif proj_high >= 100:
            seven_d["verdict"] = "tight"
        else:
            seven_d["verdict"] = "clear"

    # Compact history for the sparkline/chart: last ~72h, thinned to <= 240 pts.
    horizon = now_ms - 72 * 3600_000
    series = [s for s in samples if s["t"] >= horizon]
    if len(series) > 240:
        step = len(series) // 240 + 1
        series = series[::step]
    hist = [{"t": s["t"], "fh": s["fh"], "sd": s["sd"]} for s in series]

    # Did last week's 7-day window peak at the cap? (real overrun context)
    prev_peak = _previous_window_peak(samples, resets)

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
            "wtd_rate_per_h": round(wtd, 3) if wtd is not None else None,
            "band": band,                              # signed err {lo, hi}
            "band_by_bucket": band_all,
            "proj_low": round(proj_low, 1) if proj_low is not None else None,
            "proj_high": round(proj_high, 1) if proj_high is not None else None,
            "max_gain_pts": round(max_gain, 1) if max_gain is not None else None,
            "final_stretch_gains": _final_stretch_gains(samples, resets,
                                                        hours_to_weekly),
            "next_reset_ms": int(next_reset_dt.timestamp() * 1000) if next_reset_dt else None,
            "hours_to_reset": round(hours_to_weekly, 2) if hours_to_weekly is not None else None,
            "anchor": anchor, "prev_window_peak": prev_peak, **seven_d,
        },
        "history": hist,
    }


def _previous_window_peak(samples, resets):
    """Peak `sd` in the most recently *completed* weekly window.

    A completed window is bounded on both sides by a reset, so we need at least
    two resets; with fewer, there's no fully-observed prior window to report.
    The lower bound is inclusive (a reset timestamp is the first sample of the
    new window) and the upper bound is exclusive (up to the next reset).
    """
    if len(resets) < 2:
        return None
    prev_reset, last_reset = resets[-2], resets[-1]
    window = [s["sd"] for s in samples if prev_reset <= s["t"] < last_reset]
    return max(window) if window else None


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
