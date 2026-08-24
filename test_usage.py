#!/usr/bin/env python3
"""Edge-case tests for the usage modeler math. Run: python3 test_usage.py

No framework - just asserts, so it runs anywhere the dashboard runs.
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


def test_anchor_survives_sampling_gap():
    # Real case: three tight Tuesday-21:00 resets, then the machine sleeps
    # over the fourth - last sample Tue 17:49, next Wed 09:18. The naive
    # timestamp would move the anchor to Wednesday morning; bracketing must
    # keep it on Tuesday ~21:00.
    def br(after, before):
        return {"after": int(after.timestamp() * 1000),
                "before": int(before.timestamp() * 1000)}
    dt = datetime.datetime
    resets = [br(dt(2026, 7, 28, 20, 58), dt(2026, 7, 28, 21, 3)),
              br(dt(2026, 8, 4, 20, 59), dt(2026, 8, 4, 21, 3)),
              br(dt(2026, 8, 11, 20, 57), dt(2026, 8, 11, 21, 2)),
              br(dt(2026, 8, 18, 17, 49), dt(2026, 8, 19, 9, 18))]   # 15.5h gap
    a = U._weekly_anchor(resets)
    assert a["weekday"] == 1, a          # Tuesday, not Wednesday
    assert a["hour"] == 20 or a["hour"] == 21, a
    nxt = U._next_weekly_reset(a, dt(2026, 8, 24, 12, 0))
    assert nxt.weekday() == 1, nxt
    assert nxt.date() == datetime.date(2026, 8, 25), nxt


def test_anchor_all_gaps_uses_midpoint():
    # No tight bracket anywhere: fall back to the newest bracket's midpoint
    # rather than its (late) trailing edge.
    dt = datetime.datetime
    resets = [{"after": int(dt(2026, 8, 18, 18, 0).timestamp() * 1000),
               "before": int(dt(2026, 8, 19, 6, 0).timestamp() * 1000)}]
    a = U._weekly_anchor(resets)
    assert a["hour"] == 0, a             # midpoint of 18:00 -> 06:00


def test_fh_window_start_from_idle_climb():
    # Idle (fh<=2) until t=1h, climbs from t=1h -> window started ~1h.
    samples = [_s(0, 1, 5), _s(1, 1, 5), _s(2, 20, 5), _s(3, 40, 5)]
    start = U._fh_window_start(samples, 3 * H)
    assert start == 1 * H, start


def test_fh_window_start_after_drop():
    # Drop at t=2h (60 -> 4) then climbing: window re-opened at the drop.
    samples = [_s(0, 40, 5), _s(1, 60, 5), _s(2, 4, 5), _s(3, 15, 5)]
    start = U._fh_window_start(samples, 3 * H)
    assert start == 2 * H, start


def test_fh_window_start_unknown_when_idle():
    samples = [_s(0, 30, 5), _s(1, 1, 5), _s(2, 1, 5)]
    assert U._fh_window_start(samples, 2 * H) is None


def test_active_rate_uses_current_week_only():
    # Reset at t=100h. Before it: heavy usage that must be ignored entirely.
    # After: 4 active samples (fh>2) 30min apart gaining 3 sd points over 1.5h.
    samples = [_s(0, 90, 10), _s(50, 90, 80),            # previous week - ignored
               _s(100, 5, 0),                             # reset
               _s(100.5, 20, 1), _s(101, 30, 2), _s(101.5, 40, 3)]
    a = U._active_rate(samples, [{"after": int(100 * H), "before": int(100 * H)}], int(101.5 * H))
    assert a is not None, a
    assert abs(a["active_hours"] - 1.5) < 1e-6, a
    assert abs(a["rate_per_h"] - 2.0) < 0.01, a   # 3 pts / 1.5h


def test_active_rate_skips_idle_and_gaps():
    # fh<=2 the whole time = idle; no active hours to measure.
    samples = [_s(0, 0, 0), _s(1, 1, 0), _s(2, 2, 0), _s(3, 1, 0)]
    assert U._active_rate(samples, [{"after": 0, "before": 0}], int(3 * H)) is None


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
