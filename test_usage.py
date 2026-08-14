#!/usr/bin/env python3
"""Edge-case tests for the usage modeler math. Run: python3 test_usage.py

No framework - just asserts, so it runs anywhere Python runs.
"""
import datetime

import usage as U

H = 3600_000  # one hour in ms


def _s(t_h, fh, sd):
    return {"t": int(t_h * H), "fh": float(fh), "sd": float(sd)}


def test_burn_rate_basic():
    # 10 -> 30 over 2h = 10 pts/h
    samples = [_s(0, 10, 5), _s(1, 20, 6), _s(2, 30, 7)]
    r = U._burn_rate(samples, "fh", 2 * H)
    assert abs(r - 10.0) < 1e-6, r


def test_burn_rate_short_span_not_wild():
    # Two samples 5 min apart climbing 20 pts must NOT yield 240 pts/h.
    samples = [_s(0, 10, 5), {"t": 5 * 60 * 1000, "fh": 30.0, "sd": 5.0}]
    r = U._burn_rate(samples, "fh", 5 * 60 * 1000)
    assert r == 0.0, ("short span should be unknowable, got", r)


def test_burn_rate_reset_as_last_sample_not_false_zero():
    # Climb, then a reset as the final sample. Must not claim a usable rate
    # from one post-reset point; returns 0.0 (idle) honestly, not a fake slope.
    samples = [_s(0, 10, 5), _s(1, 30, 5), _s(2, 50, 5),
               _s(3, 2, 5)]  # reset on fh at the end
    r = U._burn_rate(samples, "fh", 3 * H)
    assert r == 0.0, r


def test_burn_rate_reset_midwindow_uses_tail():
    # Reset at t=2h, then a clean climb 5->25 over 2h post-reset = 10 pts/h.
    samples = [_s(0, 80, 5), _s(1, 90, 5), _s(2, 5, 5),
               _s(3, 15, 5), _s(4, 25, 5)]
    r = U._burn_rate(samples, "fh", 4 * H)
    assert abs(r - 10.0) < 1e-6, r


def test_project_over_and_capped():
    p = U._project(pct=30.0, rate_per_h=2.0, hours_to_reset=100.0)
    assert p["verdict"] == "over", p
    assert p["pct_at_reset"] > 100, p
    assert p["pct_at_reset_capped"] == 100.0, p


def test_project_clear_when_idle():
    p = U._project(pct=30.0, rate_per_h=0.0, hours_to_reset=100.0)
    assert p["verdict"] == "clear", p
    assert p["hours_to_full"] is None, p


def test_project_tight_band():
    # Fills at ~ the same time it resets -> tight.
    p = U._project(pct=50.0, rate_per_h=0.5, hours_to_reset=100.0)
    # 50 remaining / 0.5 = 100h to full == 100h to reset -> tight
    assert p["verdict"] == "tight", p


def test_previous_window_peak_needs_two_resets():
    samples = [_s(0, 0, 10), _s(1, 0, 40)]
    assert U._previous_window_peak(samples, []) is None
    assert U._previous_window_peak(samples, [1 * H]) is None  # only one reset


def test_previous_window_peak_inclusive_lower_bound():
    # window between reset@1h and reset@3h; peak inside should be found,
    # including the sample exactly at the lower reset boundary.
    samples = [_s(0, 0, 90),   # before prev window
               _s(1, 0, 20),   # == prev_reset (inclusive)
               _s(2, 0, 55),   # peak of the completed window
               _s(3, 0, 5)]    # == last_reset (exclusive)
    peak = U._previous_window_peak(samples, [1 * H, 3 * H])
    assert peak == 55.0, peak


def test_next_weekly_reset_rolls_forward_whole_weeks():
    anchor = {"weekday": 1, "hour": 22, "minute": 10,
              "last_reset_ms": int(datetime.datetime(2026, 8, 11, 22, 10).timestamp() * 1000)}
    now = datetime.datetime(2026, 8, 14, 12, 0)  # Fri after the Tue reset
    nxt = U._next_weekly_reset(anchor, now)
    assert nxt == datetime.datetime(2026, 8, 18, 22, 10), nxt  # next Tue
    # exactly at a reset instant -> should return the following week, never past
    now2 = datetime.datetime(2026, 8, 18, 22, 10)
    nxt2 = U._next_weekly_reset(anchor, now2)
    assert nxt2 == datetime.datetime(2026, 8, 25, 22, 10), nxt2


def test_empty_and_missing():
    assert U.load_usage(path="/no/such/file.json").get("available") is False
    assert U._read_samples("/no/such/file.json") == []


def test_single_sample_no_crash():
    assert U._burn_rate([_s(0, 5, 5)], "fh", 0) == 0.0


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print("  ok  %s" % t.__name__)
    print("\n%d/%d passed" % (passed, len(tests)))


if __name__ == "__main__":
    run()
