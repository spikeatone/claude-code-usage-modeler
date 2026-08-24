#!/usr/bin/env python3
"""The Claude Code usage modeler page.

Rendered at / by serve.py from the model that usage.load_usage()
builds off the local `/usage` history. The page is deliberately in the same
visual system as the portfolio dashboard (same tokens, same card language) so it
reads as one more panel of the same tool - just pointed at the tool itself
rather than the apps.

The question it answers: at my current burn, do I run out before the window
resets? And the two levers that change that answer - how many more hours I sit
in sessions, and whether I turn on Ultracode (which multiplies burn, it is not a
plan upgrade). All the what-if math runs client-side so the sliders are instant;
the server just ships the current state and the recent history.
"""

import html
import json


def _esc(value):
    return html.escape(str(value), quote=True)


def render_usage(model):
    """Return the full HTML page for the usage modeler."""
    data = json.dumps(model)
    return PAGE.replace("__DATA__", data)


# The page is one big template with a small client app. __DATA__ is replaced
# with the JSON model. Braces are literal here (no .format()), so the JS is
# written normally.
PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Code Usage &mdash; Postmark Digital</title>
<style>
  :root {
    --bg:#f6f7f9; --card:#ffffff; --ink:#15181d; --muted:#6b7280; --line:#e5e7eb;
    --live:#128a4b; --live-bg:#e7f6ee; --review:#b7791f; --review-bg:#fdf5e6;
    --build:#5b6472; --build-bg:#eef0f3; --dev:#7c5cd6; --dev-bg:#f0ebfb;
    --warn:#c23934; --warn-bg:#fdecea; --ready:#12694b; --accent:#2f6feb; --accent-bg:#e8effc;
    --track:#e9ebef;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg:#0e1116; --card:#171b22; --ink:#e8eaed; --muted:#9aa3af; --line:#242a33;
      --live:#3ddc84; --live-bg:#12281c; --review:#e2b155; --review-bg:#2a2113;
      --build:#9aa3af; --build-bg:#1e242c; --dev:#b49bf0; --dev-bg:#1f1830;
      --warn:#ff6b63; --warn-bg:#2a1614; --ready:#3ddc84; --accent:#5b8cff; --accent-bg:#16233d;
      --track:#232a34;
    }
  }
  :root[data-theme="dark"] {
    --bg:#0e1116; --card:#171b22; --ink:#e8eaed; --muted:#9aa3af; --line:#242a33;
    --live:#3ddc84; --live-bg:#12281c; --review:#e2b155; --review-bg:#2a2113;
    --build:#9aa3af; --build-bg:#1e242c; --dev:#b49bf0; --dev-bg:#1f1830;
    --warn:#ff6b63; --warn-bg:#2a1614; --ready:#3ddc84; --accent:#5b8cff; --accent-bg:#16233d;
    --track:#232a34;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width:1100px; margin:0 auto; padding:32px 20px 72px; }
  a { color:var(--accent); }
  header { display:flex; align-items:baseline; justify-content:space-between;
    flex-wrap:wrap; gap:8px; margin-bottom:6px; }
  h1 { font-size:22px; margin:0; letter-spacing:-0.01em; }
  .back { font-size:13px; text-decoration:none; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:22px; }
  .tabnum { font-variant-numeric:tabular-nums; }

  .stale-banner { border-radius:12px; padding:12px 18px; margin-bottom:16px;
    background:var(--review-bg); color:var(--review); font-size:13.5px;
    border:1px solid transparent; }
  .stale-banner b { color:var(--review); }

  /* manual per-model cap entry */
  .manual { display:flex; align-items:center; gap:10px; flex-wrap:wrap;
    font-size:13px; color:var(--muted); }
  .manual input[type=number] { font:inherit; font-size:14px; width:76px;
    color:var(--ink); background:var(--bg); border:1px solid var(--line);
    border-radius:8px; padding:5px 8px; font-variant-numeric:tabular-nums; }
  .manual input[type=number]:focus { outline:none; border-color:var(--accent); }
  .manual .asof { font-size:12px; }
  .manual .asof.old { color:var(--review); }
  .manual button { font:inherit; font-size:12px; color:var(--muted);
    background:none; border:1px solid var(--line); border-radius:7px;
    padding:3px 10px; cursor:pointer; }
  .manual button:hover { border-color:var(--accent); color:var(--accent); }
  .cols3 { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
  @media (max-width:900px) { .cols3 { grid-template-columns:1fr; } }

  /* Verdict band */
  .verdict { border-radius:16px; padding:20px 24px; margin-bottom:24px;
    border:1px solid var(--line); display:flex; align-items:center; gap:20px;
    flex-wrap:wrap; }
  .verdict .light { width:14px; height:14px; border-radius:50%; flex:none;
    box-shadow:0 0 0 4px color-mix(in srgb, currentColor 22%, transparent); }
  .verdict .vmain { display:flex; flex-direction:column; gap:3px; min-width:200px; }
  .verdict .vtag { font-size:22px; font-weight:700; letter-spacing:-0.01em; }
  .verdict .vsay { color:var(--muted); font-size:13.5px; max-width:56ch; }
  .verdict.v-clear { background:var(--live-bg); color:var(--live); border-color:transparent; }
  .verdict.v-tight { background:var(--review-bg); color:var(--review); border-color:transparent; }
  .verdict.v-over  { background:var(--warn-bg);  color:var(--warn);  border-color:transparent; }
  .verdict .vsay, .verdict .vtag { color:var(--ink); }
  .verdict.v-clear .vtag { color:var(--ready); }
  .verdict.v-tight .vtag { color:var(--review); }
  .verdict.v-over  .vtag { color:var(--warn); }

  .cols { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  @media (max-width:720px) { .cols { grid-template-columns:1fr; } }
  .panel { background:var(--card); border:1px solid var(--line); border-radius:14px;
    padding:18px 20px; display:flex; flex-direction:column; gap:14px; }
  .panel h2 { font-size:13px; margin:0; text-transform:uppercase; letter-spacing:.05em;
    color:var(--muted); font-weight:600; display:flex; justify-content:space-between; }
  .pill { font-size:11px; font-weight:600; padding:2px 9px; border-radius:20px;
    text-transform:uppercase; letter-spacing:.03em; }
  .pill.clear { color:var(--ready); background:var(--live-bg); }
  .pill.tight { color:var(--review); background:var(--review-bg); }
  .pill.over  { color:var(--warn); background:var(--warn-bg); }
  .pct { font-size:40px; font-weight:700; letter-spacing:-0.02em; line-height:1;
    font-variant-numeric:tabular-nums; }
  .pct small { font-size:18px; font-weight:600; color:var(--muted); }

  /* burn-down bar: consumed (solid) + projected (hatched) up to a cap line */
  .bar { position:relative; height:26px; border-radius:8px; background:var(--track);
    overflow:hidden; }
  .bar .now { position:absolute; left:0; top:0; bottom:0; border-radius:8px 0 0 8px; }
  .bar .proj { position:absolute; top:0; bottom:0; opacity:.5;
    background-image:repeating-linear-gradient(45deg, currentColor 0 6px, transparent 6px 12px); }
  .bar.clear .now { background:var(--live); } .bar.clear .proj { color:var(--live); }
  .bar.tight .now { background:var(--review); } .bar.tight .proj { color:var(--review); }
  .bar.over  .now { background:var(--warn); } .bar.over .proj { color:var(--warn); }
  .bar .cap { position:absolute; top:-3px; bottom:-3px; width:2px; background:var(--ink);
    opacity:.55; }
  .barnote { display:flex; justify-content:space-between; font-size:12px; color:var(--muted);
    font-variant-numeric:tabular-nums; }
  .rows { display:flex; flex-direction:column; gap:7px; font-size:13.5px; }
  .row { display:flex; justify-content:space-between; gap:12px; }
  .row .k { color:var(--muted); }
  .row .v { font-weight:600; font-variant-numeric:tabular-nums; text-align:right; }
  .row .v.warn { color:var(--warn); }
  .row .v.good { color:var(--ready); }

  /* history chart */
  .chartcard { margin-top:16px; background:var(--card); border:1px solid var(--line);
    border-radius:14px; padding:18px 20px; }
  .chartcard h2 { font-size:13px; margin:0 0 4px; text-transform:uppercase;
    letter-spacing:.05em; color:var(--muted); font-weight:600; }
  .legend { display:flex; gap:16px; font-size:12px; color:var(--muted); margin-bottom:8px; }
  .legend span { display:inline-flex; align-items:center; gap:6px; }
  .swatch { width:20px; height:3px; border-radius:2px; display:inline-block; }
  #chart { width:100%; height:180px; display:block; }

  /* controls */
  .controls { margin-top:16px; background:var(--card); border:1px solid var(--line);
    border-radius:14px; padding:18px 20px; }
  .controls h2 { font-size:13px; margin:0 0 4px; text-transform:uppercase;
    letter-spacing:.05em; color:var(--muted); font-weight:600; }
  .controls .hint { color:var(--muted); font-size:12.5px; margin-bottom:16px; max-width:70ch; }
  .ctl { display:grid; grid-template-columns:190px 1fr 64px; align-items:center; gap:14px;
    margin-bottom:14px; }
  @media (max-width:560px) { .ctl { grid-template-columns:1fr; gap:4px; } }
  .ctl label { font-size:13.5px; }
  .ctl label small { color:var(--muted); display:block; font-size:11.5px; font-weight:400; }
  .ctl input[type=range] { width:100%; accent-color:var(--accent); }
  .ctl output { font-weight:700; font-variant-numeric:tabular-nums; text-align:right;
    font-size:15px; }
  .presets { display:flex; align-items:center; gap:8px; margin:-6px 0 16px; flex-wrap:wrap; }
  .presets .plabel { font-size:11px; color:var(--muted); text-transform:uppercase;
    letter-spacing:.05em; }
  .preset { font:inherit; font-size:12px; padding:4px 12px; border-radius:999px; cursor:pointer;
    border:1px solid var(--line); background:var(--card); color:var(--ink); }
  .preset:hover { border-color:var(--accent); }
  .preset.on { background:var(--accent); border-color:var(--accent); color:#fff; }
  .ultra { display:flex; align-items:flex-start; gap:12px; margin-top:8px; padding:14px 16px;
    border-radius:12px; background:var(--dev-bg); border:1px solid transparent; }
  .ultra .u-ic { width:30px; height:30px; border-radius:8px; flex:none; display:grid;
    place-items:center; background:var(--dev); color:#fff; font-weight:700; font-size:13px; }
  .ultra .u-body { font-size:13px; color:var(--ink); }
  .ultra .u-body b { color:var(--dev); }
  .ultra .u-verdict { font-weight:700; }

  footer { color:var(--muted); font-size:12px; margin-top:26px; line-height:1.6; }
  .na { background:var(--card); border:1px solid var(--line); border-radius:14px;
    padding:30px; color:var(--muted); }
  /* first-run onboarding */
  .welcome { background:var(--card); border:1px solid var(--line); border-radius:16px;
    padding:26px 28px; max-width:640px; }
  .w-head { display:flex; gap:16px; align-items:flex-start; margin-bottom:22px; }
  .w-badge { width:40px; height:40px; border-radius:10px; flex:none; display:grid;
    place-items:center; font-weight:700; font-size:14px; color:#fff;
    background:linear-gradient(135deg,var(--accent),#7aa2ff); }
  .w-title { font-size:19px; font-weight:700; letter-spacing:-0.01em; }
  .w-sub { color:var(--muted); font-size:13.5px; margin-top:4px; max-width:52ch; }
  .steps { list-style:none; margin:0 0 20px; padding:0; display:flex;
    flex-direction:column; gap:16px; }
  .step { display:flex; gap:14px; align-items:flex-start; }
  .step-dot { width:24px; height:24px; border-radius:50%; flex:none; display:grid;
    place-items:center; font-size:13px; font-weight:700; border:1.5px solid var(--line);
    color:var(--muted); }
  .step-done .step-dot { background:var(--live-bg); color:var(--ready); border-color:transparent; }
  .step-wait .step-dot { background:var(--accent-bg); color:var(--accent); border-color:transparent;
    animation:pulse 1.6s ease-in-out infinite; }
  .step-title { font-weight:600; font-size:14.5px; }
  .step-done .step-title { color:var(--muted); }
  .step-body { color:var(--muted); font-size:13px; margin-top:2px; max-width:56ch; }
  .step-body code, .w-detail code, .w-muted code { background:var(--bg);
    border:1px solid var(--line); border-radius:5px; padding:0 5px; font-size:12px; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.45} }
  @media (prefers-reduced-motion: reduce) { .step-wait .step-dot { animation:none; } }
  .w-detail { border-top:1px solid var(--line); padding-top:14px; margin-bottom:16px;
    display:flex; flex-direction:column; gap:8px; }
  .w-detail-row { display:flex; gap:12px; align-items:baseline; font-size:13px; }
  .w-detail-row .k { color:var(--muted); width:96px; flex:none; }
  .w-detail .path { word-break:break-all; }
  .w-detail .yes { color:var(--ready); font-weight:600; }
  .w-detail .no { color:var(--muted); }
  .w-actions { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
  .w-btn { font:inherit; font-size:13.5px; font-weight:600; color:#fff;
    background:var(--accent); border:none; border-radius:8px; padding:7px 16px; cursor:pointer; }
  .w-btn:hover { filter:brightness(1.05); }
  .w-muted { color:var(--muted); font-size:12.5px; }
  .w-poll-dot { width:8px; height:8px; border-radius:50%; background:var(--line); }
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Claude Code usage</h1>
      <a class="back" href="/" onclick="location.reload();return false;">&#8635; refresh</a>
    </header>
    <div class="sub" id="sub">how your usage is tracking against the reset.</div>
    <div id="app"></div>
    <footer id="foot"></footer>
  </div>
<script>
var MODEL = __DATA__;

// Model burn factors, derived from Anthropic's published API pricing (per MTok
// in/out): Fable 5 $10/$50, Opus 5 & Opus 4.8 $5/$25, Sonnet 5 $3/$15 (intro
// $2/$10 through 2026-08-31). The input and output ratios agree exactly, so the
// factor is unambiguous: Fable = 2.0x Opus, Sonnet = 0.6x Opus. Baseline 1.0 is
// Opus — the model this machine's measured burn history ran on.
var MODELS = [
  { name: "Fable", mult: 2.0 },
  { name: "Opus", mult: 1.0 },
  { name: "Sonnet", mult: 0.6 }
];
// Effort stops modulate token *volume*, not per-token price — Anthropic
// publishes no cost figures for them, so these are estimates relative to Extra
// (xhigh), Claude Code's default and this tool's measured baseline. Ultracode is
// multi-agent orchestration on top of max effort (~2.5x, the tool's original
// calibration).
var EFFORTS = [
  { name: "Low", mult: 0.4 },
  { name: "Medium", mult: 0.6 },
  { name: "High", mult: 0.8 },
  { name: "Extra", mult: 1.0 },
  { name: "Max", mult: 1.4 },
  { name: "Ultracode", mult: 2.5 }
];

function fmtHours(h) {
  if (h === null || h === undefined) return "—";
  if (h < 1) return Math.round(h * 60) + " min";
  if (h < 48) return (Math.round(h * 10) / 10) + " h";
  return (Math.round(h / 24 * 10) / 10) + " d";
}
function fmtWhen(ms) {
  if (!ms) return "—";
  var d = new Date(ms);
  var days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  var hh = d.getHours(), mm = d.getMinutes();
  var ampm = hh >= 12 ? "pm" : "am"; var h12 = hh % 12; if (h12 === 0) h12 = 12;
  return days[d.getDay()] + " " + h12 + ":" + (mm < 10 ? "0" : "") + mm + ampm;
}
function classFor(v) { return v === "over" ? "over" : (v === "tight" ? "tight" : "clear"); }

// Client-side projection so the sliders recompute instantly. Mirrors _project()
// in usage.py. `bandPts` is the calibrated +/- uncertainty (from the server's
// backtest of this user's own history); when given, the verdict judges the
// RANGE, not the point: over only when even the optimistic edge busts.
// Projection = a PLAN, not a forecast. Current %, hours left, and the rate
// the sliders describe. No inference from past weeks by design.
function project(pct, ratePerH, hoursToReset) {
  var remaining = Math.max(0, 100 - pct);
  var hoursToFull = ratePerH <= 0.0001 ? null : remaining / ratePerH;
  var pctAtReset = (hoursToReset == null) ? null :
      (ratePerH <= 0.0001 ? pct : pct + ratePerH * hoursToReset);
  var verdict;
  if (hoursToReset == null) verdict = "unknown";
  else if (pctAtReset == null || pctAtReset < 90) verdict = "clear";
  else if (pctAtReset <= 100) verdict = "tight";
  else verdict = "over";
  return { hoursToFull: hoursToFull, pctAtReset: pctAtReset, verdict: verdict };
}

function barHTML(pct, projPct, cls) {
  var now = Math.max(0, Math.min(100, pct));
  var projTop = Math.max(now, Math.min(100, projPct == null ? now : projPct));
  var projW = projTop - now;
  return '<div class="bar ' + cls + '">' +
    '<div class="now" style="width:' + now + '%"></div>' +
    (projW > 0.3 ? '<div class="proj" style="left:' + now + '%;width:' + projW + '%"></div>' : '') +
    '<div class="cap" style="left:100%"></div></div>';
}

function panelHTML(title, meta, state) {
  var cls = classFor(state.verdict);
  var projShow = state.pctAtReset == null ? null : Math.round(state.pctAtReset);
  var projLabel = projShow == null ? "\u2014" :
      (projShow > 100 ? (projShow + "% \u2014 over by " + (projShow - 100)) : projShow + "%");
  var rows = '';
  rows += metaRow(meta.rateLabel || "Burn rate now", meta.rate.toFixed(meta.rateDp) + " pts/hr");
  if (meta.rate2 != null) rows += metaRow("Burst rate (last ~2h)", meta.rate2.toFixed(2) + " pts/hr");
  if (meta.resetLabel) rows += metaRow("Window resets", meta.resetLabel);
  rows += metaRow("Time to reset", fmtHours(meta.hoursToReset));
  rows += metaRow("Hits 100% in", fmtHours(state.hoursToFull),
                  state.verdict === "over" ? "warn" : "");
  rows += metaRow("Projected at reset", projLabel,
                  state.verdict === "over" ? "warn" : (state.verdict === "clear" ? "good" : ""));
  return '<div class="panel">' +
    '<h2>' + title + '<span class="pill ' + cls + '">' + state.verdict + '</span></h2>' +
    '<div class="pct tabnum">' + Math.round(meta.pct) + '<small>%</small></div>' +
    barHTML(meta.pct, state.pctAtReset, cls) +
    '<div class="barnote"><span>now ' + Math.round(meta.pct) + '%</span>' +
      '<span>' + (projShow == null ? '' : ('projected ' + Math.min(100, projShow) + '%' + (projShow > 100 ? '+' : ''))) + '</span>' +
      '<span>100%</span></div>' +
    '<div class="rows">' + rows + '</div></div>';
}
function metaRow(k, v, vc) {
  return '<div class="row"><span class="k">' + k + '</span>' +
    '<span class="v ' + (vc || '') + '">' + v + '</span></div>';
}

function verdictBand(worst, fiveState, sevenState) {
  var cls = classFor(worst);
  var tag = worst === "over" ? "PULL BACK" : (worst === "tight" ? "HOLD STEADY" : "ROOM TO PUSH");
  var say;
  if (worst === "over") {
    say = sevenState.verdict === "over"
      ? "This plan runs out of weekly budget before the reset. Cut the hours, the model, or the effort."
      : "This 5-hour burst will top out the session window before it rolls over.";
  } else if (worst === "tight") {
    say = "This plan lands you right around the limit before the reset — no cushion. Fine, but watch it.";
  } else {
    say = "This plan finishes inside both windows with room to spare. Push harder with the sliders to see where it tips.";
  }
  return '<div class="verdict v-' + cls + '"><div class="light" style="background:currentColor"></div>' +
    '<div class="vmain"><div class="vtag">' + tag + '</div>' +
    '<div class="vsay">' + say + '</div></div></div>';
}

function worstOf(a, b) {
  var rank = { over: 3, tight: 2, clear: 1, unknown: 0 };
  return rank[a] >= rank[b] ? a : b;
}

function drawChart(hist) {
  var c = document.getElementById("chart");
  if (!c || !hist || !hist.length) return;
  var dpr = window.devicePixelRatio || 1;
  var W = c.clientWidth, Hh = c.clientHeight;
  c.width = W * dpr; c.height = Hh * dpr;
  var g = c.getContext("2d"); g.scale(dpr, dpr);
  var pad = { l: 28, r: 8, t: 10, b: 18 };
  var iw = W - pad.l - pad.r, ih = Hh - pad.t - pad.b;
  var t0 = hist[0].t, t1 = hist[hist.length - 1].t;
  var span = Math.max(1, t1 - t0);
  var cs = getComputedStyle(document.documentElement);
  var line = cs.getPropertyValue("--line").trim() || "#e5e7eb";
  var muted = cs.getPropertyValue("--muted").trim() || "#888";
  var accent = cs.getPropertyValue("--accent").trim() || "#2f6feb";
  var warn = cs.getPropertyValue("--warn").trim() || "#c23934";
  function X(t) { return pad.l + (t - t0) / span * iw; }
  function Y(p) { return pad.t + (1 - p / 100) * ih; }
  // gridlines at 0/50/100
  g.strokeStyle = line; g.fillStyle = muted; g.lineWidth = 1;
  g.font = "10px -apple-system,sans-serif"; g.textBaseline = "middle";
  [0, 50, 100].forEach(function (p) {
    g.beginPath(); g.moveTo(pad.l, Y(p)); g.lineTo(W - pad.r, Y(p)); g.stroke();
    g.fillText(p + "", 4, Y(p));
  });
  function plot(key, color) {
    g.strokeStyle = color; g.lineWidth = 1.75; g.beginPath();
    hist.forEach(function (s, i) {
      var x = X(s.t), y = Y(s[key]);
      if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
    });
    g.stroke();
  }
  plot("sd", warn);      // weekly
  plot("fh", accent);    // five-hour
  // time axis: label ends
  g.fillStyle = muted; g.textBaseline = "alphabetic";
  var d0 = new Date(t0), d1 = new Date(t1);
  g.fillText((d0.getMonth() + 1) + "/" + d0.getDate(), pad.l, Hh - 5);
  g.textAlign = "right";
  g.fillText((d1.getMonth() + 1) + "/" + d1.getDate() + " now", W - pad.r, Hh - 5);
  g.textAlign = "left";
}

// First-run onboarding. There is no account login - the tool reads the usage
// file Claude Code writes to *this* machine's disk. So "connect your account"
// really means "have Claude Code installed and let it record usage once". We
// detect that automatically and poll so the dashboard appears the moment the
// file shows up.
function renderOnboarding(app) {
  var m = MODEL || {};
  var primary = m.primary_path || "~/Library/Application Support/Claude/plan-usage-history.json";
  var fileExists = !!m.file_exists;
  var step2state = fileExists ? "done" : "todo";

  app.innerHTML =
    '<div class="welcome">' +
      '<div class="w-head"><div class="w-badge">CC</div>' +
        '<div><div class="w-title">Let&rsquo;s connect your Claude Code usage</div>' +
        '<div class="w-sub">Your data never leaves this machine &mdash; this reads the ' +
        'usage file Claude Code saves on your own computer. There&rsquo;s no login and ' +
        'nothing to paste.</div></div></div>' +

      '<ol class="steps">' +
        stepHTML("done", "Install Claude Code",
          "If you can run <code>claude</code> in a terminal, you&rsquo;re set. " +
          "Otherwise grab it from <a href=\"https://claude.com/claude-code\" target=\"_blank\" rel=\"noopener\">claude.com/claude-code</a>.") +
        stepHTML(step2state, "Let it record your usage once",
          "In any Claude Code session, run <code>/usage</code>. That makes Claude Code " +
          "start sampling your 5-hour and 7-day limits (about every 15 minutes) to a " +
          "local file. You only need to do this once; it keeps updating after.") +
        stepHTML("wait", "This page picks it up automatically",
          "<span id=\"poll-msg\">Watching for your usage file&hellip;</span> " +
          "As soon as Claude Code has written some samples, the dashboard loads here on its own.") +
      '</ol>' +

      '<div class="w-detail">' +
        '<div class="w-detail-row"><span class="k">Looking for</span>' +
          '<code class="path">' + primary + '</code></div>' +
        '<div class="w-detail-row"><span class="k">File present</span>' +
          '<span class="' + (fileExists ? "yes" : "no") + '">' +
          (fileExists ? "yes — waiting for the first samples" : "not yet") + '</span></div>' +
      '</div>' +

      '<div class="w-actions">' +
        '<button class="w-btn" id="w-recheck">Check now</button>' +
        '<span class="w-poll-dot" id="w-dot"></span>' +
        '<span class="w-muted">or reload the page after running <code>/usage</code></span>' +
      '</div>' +
    '</div>';

  var rc = document.getElementById("w-recheck");
  if (rc) rc.addEventListener("click", pollNow);
  startPolling();
}

function stepHTML(state, title, body) {
  var mark = state === "done" ? "✓" : (state === "wait" ? "…" : "");
  return '<li class="step step-' + state + '">' +
    '<span class="step-dot">' + mark + '</span>' +
    '<div><div class="step-title">' + title + '</div>' +
    '<div class="step-body">' + body + '</div></div></li>';
}

var _pollTimer = null, _polling = false;
function startPolling() {
  if (_pollTimer) return;
  _pollTimer = setInterval(pollNow, 8000);   // gentle - the file updates ~15 min
}
function pollNow() {
  if (_polling) return;
  _polling = true;
  var dot = document.getElementById("w-dot");
  if (dot) dot.classList.add("on");
  fetch("/api/usage", { cache: "no-store" }).then(function (r) { return r.json(); })
    .then(function (fresh) {
      _polling = false;
      if (dot) dot.classList.remove("on");
      if (fresh && fresh.available) {
        clearInterval(_pollTimer); _pollTimer = null;
        MODEL = fresh; render();               // real dashboard takes over
      } else {
        MODEL = fresh || MODEL;
        var pm = document.getElementById("poll-msg");
        if (pm && fresh && fresh.file_exists)
          pm.textContent = "Found your file — waiting for the first samples…";
      }
    })
    .catch(function () { _polling = false; if (dot) dot.classList.remove("on"); });
}

// The per-model weekly cap (e.g. "Weekly - Fable") is shown by /usage but is
// NOT written to plan-usage-history.json, so it can't be read from disk. The
// user types it; we stamp when, because a typed number goes stale in a way a
// sampled one doesn't - past ~6h we stop letting it drive the verdict.
var FABLE_KEY = "usage.fablePct", FABLE_AT = "usage.fablePctAt";
var FABLE_STALE_H = 6;

function readFable() {
  try {
    var v = parseFloat(localStorage.getItem(FABLE_KEY));
    var at = parseFloat(localStorage.getItem(FABLE_AT));
    if (!isFinite(v)) return null;
    return { pct: Math.max(0, Math.min(100, v)),
             at: isFinite(at) ? at : null };
  } catch (e) { return null; }
}
function writeFable(pct) {
  try {
    if (pct == null || !isFinite(pct)) {
      localStorage.removeItem(FABLE_KEY); localStorage.removeItem(FABLE_AT);
    } else {
      localStorage.setItem(FABLE_KEY, Math.max(0, Math.min(100, pct)));
      localStorage.setItem(FABLE_AT, Date.now());
    }
  } catch (e) { /* storage off - just don't persist */ }
}
function fableAgeH(f) {
  return (f && f.at) ? (Date.now() - f.at) / 3600000 : null;
}

function render() {
  var app = document.getElementById("app");
  if (!MODEL || !MODEL.available) { renderOnboarding(app); return; }
  var five = MODEL.five_hour, seven = MODEL.seven_day;

  // read controls. On first paint the inputs don't exist yet, so restore the
  // last session's values from localStorage (falling back to defaults: Opus at
  // Extra effort = 1.0x, the measured baseline). Every paint writes them back,
  // so the settings stay sticky across reloads/sessions.
  var aEl = document.getElementById("f-active");
  var eEl = document.getElementById("f-effort");
  var sActive = parseFloat(localStorage.getItem("usage.activeHours"));
  var sEffort = parseInt(localStorage.getItem("usage.effort"), 10);
  var activeHours = aEl ? parseFloat(aEl.value) : (isFinite(sActive) ? sActive : 6);
  var effortIdx = eEl ? parseInt(eEl.value, 10) : (isFinite(sEffort) ? sEffort : 3);
  effortIdx = Math.min(Math.max(effortIdx, 0), EFFORTS.length - 1);
  var modelName = localStorage.getItem("usage.model") || "Opus";
  var model = MODELS.filter(function (m) { return m.name === modelName; })[0] || MODELS[1];
  var effort = EFFORTS[effortIdx];
  var mult = model.mult * effort.mult;
  try {
    localStorage.setItem("usage.activeHours", activeHours);
    localStorage.setItem("usage.effort", effortIdx);
    localStorage.setItem("usage.model", model.name);
  } catch (e) { /* private mode / storage off — just don't persist */ }

  // The plan: your slider hours/day at the measured pace-while-active for
  // THIS week, times model x effort. Nothing from past weeks feeds this.
  var activeRate = (seven.active && seven.active.rate_per_h) || seven.rate_per_h || 0;
  var burst = seven.rate_per_h || 0;
  var sevenRateEff = activeRate * (activeHours / 24) * mult;
  var sevenState = project(seven.pct, sevenRateEff, seven.hours_to_reset);
  // 5-hour window: the live burst over the real remaining horizon.
  var fiveRateEff = five.rate_per_h * mult;
  var fiveHorizon = five.horizon_h != null ? five.horizon_h : five.window_h;
  var fiveState = project(five.pct, fiveRateEff, fiveHorizon);

  var fiveReset = five.resets_by_ms
      ? ("by ~" + fmtWhen(five.resets_by_ms))
      : "\u22645h (window start unknown)";
  var fivePanel = panelHTML("5-hour session window", {
    pct: five.pct, rate: fiveRateEff, rateDp: 1,
    hoursToReset: fiveHorizon, resetLabel: fiveReset
  }, fiveState);
  var sevenPanel = panelHTML("7-day weekly window", {
    pct: seven.pct, rate: sevenRateEff, rateDp: 2,
    rateLabel: "Planned pace", rate2: burst * mult,
    hoursToReset: seven.hours_to_reset, resetLabel: fmtWhen(seven.next_reset_ms)
  }, sevenState);

  // Third gauge: the manually-entered per-model weekly cap. It shares the
  // weekly reset clock and burns at the planned pace whenever the selected
  // model IS that model - otherwise it just sits where it was entered.
  var fable = readFable();
  var fableAge = fableAgeH(fable);
  var fableFresh = fable && (fableAge == null || fableAge <= FABLE_STALE_H);
  var fableState = null, fablePanel = "", ageTxtOut = "";
  if (fable) {
    var onFable = model.name === "Fable";
    var fableRate = onFable ? sevenRateEff : 0;
    fableState = project(fable.pct, fableRate, seven.hours_to_reset);
    ageTxtOut = fableAge == null ? "" :
        (fableAge < 1 ? "entered just now"
         : fableAge < 24 ? ("entered " + Math.round(fableAge) + "h ago")
         : ("entered " + Math.round(fableAge / 24) + "d ago"));
    if (!fableFresh) ageTxtOut += " \u2014 stale, not driving the verdict";
    fablePanel = panelHTML("Weekly \u00b7 Fable (entered)", {
      pct: fable.pct,
      rate: fableRate, rateDp: 2,
      rateLabel: onFable ? "Planned pace" : "Planned pace (not on Fable)",
      hoursToReset: seven.hours_to_reset,
      resetLabel: fmtWhen(seven.next_reset_ms)
    }, fableState);
  }

  // The binding constraint wins. A stale typed number informs but never drives.
  var worst = worstOf(fiveState.verdict, sevenState.verdict);
  if (fableState && fableFresh) worst = worstOf(worst, fableState.verdict);

  // Ultracode read-out: what does the top effort stop (~2.5x fan-out) do to the
  // weekly window on the currently selected model? Same WTD base and band as
  // the main projection, and the real reset day - not a hardcoded "Tuesday"
  // (this account's reset has already moved once).
  var resetDay = seven.next_reset_ms
      ? ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"][new Date(seven.next_reset_ms).getDay()]
      : "the reset";
  var ultraOn = project(seven.pct, activeRate * (activeHours / 24) * model.mult * 2.5,
                        seven.hours_to_reset);
  var ultraMsg;
  if (seven.pct >= 99) {
    ultraMsg = 'You&rsquo;re at the weekly cap now — Ultracode has nothing left to spend until ' + resetDay + '.';
  } else if (ultraOn.verdict === "over") {
    var by = ultraOn.pctAtReset ? Math.round(ultraOn.pctAtReset - 100) : null;
    ultraMsg = 'At ~2.5× burn, Ultracode would <b>blow past the weekly limit</b>' +
      (by && by > 0 ? ' by ~' + by + '%' : '') + ' before ' + resetDay + '. Save it for a lighter week.';
  } else if (ultraOn.verdict === "tight") {
    ultraMsg = 'Ultracode (~2.5× burn) <b>could land you at the weekly limit</b> before ' + resetDay + ' — inside the uncertainty band. Doable for a focused push, but no cushion.';
  } else {
    ultraMsg = 'Your weekly budget can <b>absorb Ultracode</b> (~2.5× burn) and still reset with room to spare. Green light.';
  }

  var prevNote = "";

  var modelBtns = MODELS.map(function (m) {
    var on = m.name === model.name ? " on" : "";
    return '<button type="button" class="preset' + on + '" data-model="' + m.name + '">' + m.name + '</button>';
  }).join("");

  // Staleness: sampling stops whenever Claude Code isn't running, and stale
  // percentages presented as "now" were a real inaccuracy. Chip when fresh,
  // banner when old.
  var ageMin = MODEL.data_age_min != null ? MODEL.data_age_min : 0;
  var staleHtml = "";
  if (ageMin > 30) {
    var ageTxt = ageMin >= 90 ? (Math.round(ageMin / 6) / 10 + " h") : (Math.round(ageMin) + " min");
    staleHtml = '<div class="stale-banner">Data is <b>' + ageTxt + ' old</b> — Claude Code ' +
      'hasn&rsquo;t sampled since ' + fmtWhen(MODEL.latest_sample_ms) +
      '. Percentages are as of then; time-to-reset is current.</div>';
  }

  app.innerHTML =
    staleHtml +
    verdictBand(worst, fiveState, sevenState) +
    '<div class="' + (fablePanel ? "cols3" : "cols") + '">' +
      fivePanel + sevenPanel + fablePanel + '</div>' +
    '<div class="chartcard"><h2>Last 72 hours</h2>' +
      '<div class="legend"><span><i class="swatch" style="background:var(--accent)"></i>5-hour window</span>' +
      '<span><i class="swatch" style="background:var(--warn)"></i>7-day window</span></div>' +
      '<canvas id="chart"></canvas></div>' +
    '<div class="controls"><h2>Model a change</h2>' +
      '<div class="hint">The burn rate above is measured from your recent sessions — ' +
      'the multipliers below are relative to that baseline (assumed Opus at Extra ' +
      'effort, Claude Code’s default). Pick the model and effort you plan to run ' +
      'and the projection updates live. Model ratios come from Anthropic’s ' +
      'published pricing; effort ratios are estimates.' + prevNote + '</div>' +
      '<div class="ctl"><label>Active hours / day<small>time actually in sessions</small></label>' +
        '<input type="range" id="f-active" min="0.5" max="16" step="0.5" value="' + activeHours + '">' +
        '<output>' + activeHours + ' h</output></div>' +
      '<div class="ctl"><label>Model<small>Fable 2× · Opus 1× · Sonnet 0.6× (published pricing)</small></label>' +
        '<div class="presets" style="margin:0">' + modelBtns + '</div>' +
        '<output>' + model.mult.toFixed(1) + '×</output></div>' +
      '<div class="ctl"><label>Effort<small>Low · Medium · High · Extra · Max · Ultracode</small></label>' +
        '<input type="range" id="f-effort" min="0" max="' + (EFFORTS.length - 1) + '" step="1" value="' + effortIdx + '">' +
        '<output>' + effort.name + '</output></div>' +
      '<div class="presets"><span class="plabel">Effective burn</span><b>' + mult.toFixed(1) + '×</b>' +
        '<span class="plabel" style="text-transform:none;letter-spacing:0">= ' + model.name + ' ' +
        model.mult.toFixed(1) + ' × ' + effort.name + ' ' + effort.mult.toFixed(1) + '</span></div>' +
      '<div class="ctl"><label>Weekly \u00b7 Fable<small>per-model cap \u2014 type it from <code>/usage</code></small></label>' +
        '<div class="manual">' +
          '<input type="number" id="f-fable" min="0" max="100" step="1" placeholder="\u2014" value="' +
            (fable ? fable.pct : "") + '">' +
          '<span>%</span>' +
          (fable ? '<span class="asof' + (fableFresh ? '' : ' old') + '">' + ageTxtOut + '</span>' +
                   '<button type="button" id="f-fable-clear">clear</button>'
                 : '<span class="asof">not tracked in the history file \u2014 enter it to model it</span>') +
        '</div>' +
        '<output>' + (fable ? Math.round(fable.pct) + "%" : "\u2014") + '</output></div>' +
      '<div class="ultra"><div class="u-ic">U</div><div class="u-body">' +
        '<b>Ultracode check.</b> ' + ultraMsg + '</div></div>' +
    '</div>';

  drawChart(MODEL.history);

  // manual per-model cap: commit on change (not each keystroke) so a
  // half-typed "9" of "95" doesn't briefly flash a wrong verdict.
  var fEl = document.getElementById("f-fable");
  if (fEl) fEl.addEventListener("change", function () {
    var v = parseFloat(fEl.value);
    writeFable(isFinite(v) ? v : null);
    render();
  });
  var fClear = document.getElementById("f-fable-clear");
  if (fClear) fClear.addEventListener("click", function () {
    writeFable(null); render();
  });

  // rewire the sliders (innerHTML replaced them)
  ["f-active", "f-effort"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", render);
  });
  // model chips persist the choice and re-project
  Array.prototype.forEach.call(document.querySelectorAll(".preset"), function (b) {
    b.addEventListener("click", function () {
      try { localStorage.setItem("usage.model", b.getAttribute("data-model")); } catch (e) {}
      render();
    });
  });
}

window.addEventListener("resize", function () { drawChart(MODEL.history); });
render();

var foot = document.getElementById("foot");
if (MODEL && MODEL.available) {
  var d = new Date(MODEL.latest_sample_ms || MODEL.now_ms);
  foot.innerHTML = 'Reading <code>~/Library/Application Support/Claude/plan-usage-history.json</code> — ' +
    MODEL.sample_count + ' samples (~5 min apart), latest ' + d.toLocaleString() + '. ' +
    'Percentages are the same ones <code>/usage</code> shows. The weekly projection is your ' +
    'week-to-date pace; the range around it is the median error of that projector, backtested ' +
    'against your own completed weeks. Read-only — nothing here changes your usage.';
}
</script>
</body>
</html>"""
