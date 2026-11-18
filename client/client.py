#!/usr/bin/env python3
"""Page-load client on plain sockets.
Loads index.html, then fetches every embedded object ONE AT A TIME.
Modes:  nonpersistent = new TCP connection + 'Connection: close' for every request
        persistent    = one TCP connection reused (HTTP/1.1 keep-alive)
--proxy HOST:PORT sends absolute-URI requests to a caching proxy instead of the origin."""
import argparse
import csv
import os
import re
import socket
import statistics
import time
from urllib.parse import urlsplit


def read_response(rfile):
    line = rfile.readline(65537)
    if not line:
        raise OSError("connection closed before response")
    parts = line.decode("iso-8859-1").strip().split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise ValueError("bad status line")
    status = int(parts[1])
    headers = {}
    while True:
        h = rfile.readline(65537)
        if h in (b"\r\n", b"\n", b""):
            break
        k, _, v = h.decode("iso-8859-1").partition(":")
        headers[k.strip().lower()] = v.strip()
    if status in (204, 304) or 100 <= status < 200:
        body = b""
    elif "content-length" in headers:
        n = int(headers["content-length"])
        body = rfile.read(n)
        if len(body) != n:
            raise OSError("short body")
    else:
        body = rfile.read()                       # read until the server closes
        headers["connection"] = "close"
    return status, headers, body


class Client:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.sock = None
        self.rfile = None
        self.connections = 0                      # number of TCP connections opened
        self.uses = 0                             # requests served on the current connection

    def _open(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.rfile = self.sock.makefile("rb")
        self.connections += 1
        self.uses = 0

    def close(self):
        if self.rfile:
            self.rfile.close()
        if self.sock:
            self.sock.close()
        self.sock = self.rfile = None

    def get(self, target, host_header, keep):
        req = (f"GET {target} HTTP/1.1\r\nHost: {host_header}\r\n"
               f"User-Agent: cn-client/1.0\r\n"
               f"Connection: {'keep-alive' if keep else 'close'}\r\n\r\n").encode()
        for attempt in (0, 1):
            if self.sock is None:
                self._open()
            reused = self.uses > 0
            try:
                self.sock.sendall(req)
                status, headers, body = read_response(self.rfile)
            except (OSError, ValueError):
                self.close()
                if reused and attempt == 0:       # server closed an idle connection: retry once
                    continue
                raise
            self.uses += 1
            if (not keep) or "close" in headers.get("connection", "").lower():
                self.close()
            return status, body


def load_page(mode, proxy, origin_hostport, page_path):
    """Load the page and return a dict of measurements."""
    keep = (mode == "persistent")
    if proxy:
        ch, cp = proxy
    else:
        ch, _, cp = origin_hostport.rpartition(":")
        cp = int(cp)
    cl = Client(ch, cp)

    def target(p):
        return f"http://{origin_hostport}{p}" if proxy else p

    t0 = time.perf_counter()
    status, body = cl.get(target(page_path), origin_hostport, keep)
    requests, total_bytes, ok = 1, len(body), (status == 200)
    base = page_path.rsplit("/", 1)[0]
    for ref in re.findall(r'src="([^"]+)"', body.decode("iso-8859-1")):
        p = ref if ref.startswith("/") else base + "/" + ref
        status, obj = cl.get(target(p), origin_hostport, keep)
        requests += 1
        total_bytes += len(obj)
        ok = ok and status == 200
    t1 = time.perf_counter()
    conns = cl.connections
    cl.close()
    return {"time": t1 - t0, "connections": conns, "requests": requests,
            "bytes": total_bytes, "ok": ok}


def clear_proxy(host, port):
    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(f"GET /__clear HTTP/1.1\r\nHost: {host}:{port}\r\n"
                  f"Connection: close\r\n\r\n".encode())
        while s.recv(4096):
            pass


def main():
    ap = argparse.ArgumentParser(description="Page-load client")
    ap.add_argument("--url", default="http://10.0.3.10:8080/index.html")
    ap.add_argument("--mode", choices=["nonpersistent", "persistent"], required=True)
    ap.add_argument("--proxy", default=None, help="HOST:PORT of the caching proxy")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--clear-proxy", action="store_true",
                    help="empty the proxy cache before every run (not timed)")
    ap.add_argument("--label", default="", help="free text stored in the CSV")
    ap.add_argument("--rtt", default="", help="RTT in ms, only stored in the CSV")
    ap.add_argument("--csv", default=None, help="append results to this CSV file")
    ap.add_argument("--pause", type=float, default=0.5, help="seconds between runs")
    args = ap.parse_args()

    u = urlsplit(args.url)
    origin_hostport = f"{u.hostname}:{u.port or 80}"
    page_path = u.path or "/"
    proxy = None
    if args.proxy:
        ph, _, pp = args.proxy.rpartition(":")
        proxy = (ph, int(pp))

    results = []
    for i in range(1, args.runs + 1):
        if proxy and args.clear_proxy:
            clear_proxy(*proxy)
        r = load_page(args.mode, proxy, origin_hostport, page_path)
        results.append(r)
        print(f"run {i}: load_time={r['time']:.4f}s connections={r['connections']} "
              f"requests={r['requests']} bytes={r['bytes']} all_ok={r['ok']}", flush=True)
        if args.csv:
            new = not os.path.exists(args.csv)
            with open(args.csv, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["label", "mode", "proxy", "rtt_ms", "run", "load_time_s",
                                "connections", "requests", "bytes", "all_ok"])
                w.writerow([args.label, args.mode, "yes" if proxy else "no", args.rtt, i,
                            f"{r['time']:.4f}", r["connections"], r["requests"],
                            r["bytes"], r["ok"]])
        if i < args.runs:
            time.sleep(args.pause)

    times = [r["time"] for r in results]
    sd = statistics.stdev(times) if len(times) > 1 else 0.0
    print(f"summary: mode={args.mode} runs={len(times)} mean={statistics.mean(times):.4f}s "
          f"stdev={sd:.4f}s min={min(times):.4f}s max={max(times):.4f}s")


if __name__ == "__main__":
    main()
