#!/usr/bin/env python3
"""Claude Code usage modeler - a tiny local server.

    python3 serve.py            serve on http://127.0.0.1:8787 and open it
    python3 serve.py --port 9000
    python3 serve.py --no-open  don't launch a browser

Reads your local Claude Code `/usage` history (the same 5-hour and 7-day
percentages the `/usage` command shows, which Claude Code samples every ~15
minutes) and projects them forward: at your current burn, do you run out before
the window resets? It is entirely read-only - it never writes your usage file -
and binds to localhost only, so nothing leaves your machine.

No dependencies beyond the Python standard library.

Endpoints:
  GET  /            the usage modeler page
  GET  /api/usage   the JSON model behind it (read-only)
"""

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import usage as usage_model
from usage_page import render_usage


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type):
        payload = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("  %s\n" % (fmt % args))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            try:
                self._send(200, render_usage(usage_model.load_usage()),
                           "text/html; charset=utf-8")
            except Exception as exc:  # noqa: BLE001
                self._send(500, "Failed to render: %s" % exc, "text/plain")
            return
        if path == "/api/usage":
            try:
                self._send(200, json.dumps(usage_model.load_usage()),
                           "application/json")
            except Exception as exc:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(exc)}), "application/json")
            return
        self._send(404, json.dumps({"error": "not found"}), "application/json")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1 - localhost only)")
    parser.add_argument("--no-open", action="store_true",
                        help="don't open a browser automatically")
    args = parser.parse_args()

    url = "http://%s:%d/" % (args.host, args.port)
    server = ThreadingHTTPServer((args.host, args.port), Handler)

    model = usage_model.load_usage()
    if not model.get("available"):
        print("Note: no usage history found yet at")
        print("  %s" % usage_model.HISTORY_PATH)
        print("Open Claude Code and run /usage once so it starts sampling, then reload.\n")

    print("Claude Code usage modeler on %s" % url)
    print("Read-only. Ctrl-C to stop.")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
