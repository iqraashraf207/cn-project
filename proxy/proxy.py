#!/usr/bin/env python3
"""Caching HTTP proxy on plain sockets.
Objectives: cache with TTL, conditional GET (If-None-Match / If-Modified-Since), request log.
Limits today: one request per client connection (Connection: close), chunked
responses unsupported, upstream uses a new TCP connection per request."""
import argparse
import email.utils
import os
import socket
import threading
import time
from datetime import datetime
from urllib.parse import urlsplit

BUFSZ = 65536
HOP_BY_HOP = {"connection", "proxy-connection", "keep-alive", "te",
              "trailer", "transfer-encoding", "upgrade"}
CONFIG = {"ttl": 30, "quiet": False}
cache = {}                      # absolute URL -> entry dict
cache_lock = threading.Lock()
log_lock = threading.Lock()
LOGF = None


def log_line(method, url, result, status, nbytes):
    line = "\t".join([datetime.now().isoformat(timespec="milliseconds"),
                      method, url, result, str(status), str(nbytes)])
    with log_lock:
        LOGF.write(line + "\n")
    if not CONFIG["quiet"]:
        print(line, flush=True)


def clear_all():
    with cache_lock:
        cache.clear()
    with log_lock:
        LOGF.truncate(0)


def parse_headers(lines):
    out = []
    for line in lines:
        if ":" in line:
            k, v = line.split(":", 1)
            out.append((k.strip(), v.strip()))
    return out


def read_head(sock):
    """Read until the blank line. Return (head_bytes, leftover) or (None, b'')."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(BUFSZ)
        if not chunk:
            break
        data += chunk
    head, sep, rest = data.partition(b"\r\n\r\n")
    return (head, rest) if sep else (None, b"")


def send_simple(csock, code, reason, text):
    body = text.encode()
    csock.sendall((f"HTTP/1.1 {code} {reason}\r\nContent-Type: text/plain\r\n"
                   f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)


def fetch_origin(method, host, port, path, headers, body=b""):
    """One request to the origin on a fresh connection. Returns a response dict."""
    out = f"{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n"
    for k, v in headers:
        out += f"{k}: {v}\r\n"
    out += "\r\n"
    with socket.create_connection((host, port), timeout=10) as us:
        us.sendall(out.encode("iso-8859-1") + body)
        head, rest = read_head(us)
        if head is None:
            raise OSError("bad response from origin")
        lines = head.decode("iso-8859-1").split("\r\n")
        parts = lines[0].split(" ", 2)
        status = int(parts[1])
        reason = parts[2] if len(parts) > 2 else ""
        hdrs = parse_headers(lines[1:])
        hd = {k.lower(): v for k, v in hdrs}
        if "chunked" in hd.get("transfer-encoding", "").lower():
            raise OSError("chunked responses not supported")
        no_body = method == "HEAD" or status in (204, 304) or 100 <= status < 200
        data = b""
        if not no_body:
            data = rest
            if "content-length" in hd:
                want = int(hd["content-length"])
                while len(data) < want:
                    chunk = us.recv(BUFSZ)
                    if not chunk:
                        break
                    data += chunk
                data = data[:want]
            else:
                while True:
                    chunk = us.recv(BUFSZ)
                    if not chunk:
                        break
                    data += chunk
    return {"status": status, "reason": reason, "headers": hdrs, "body": data}


def freshness(hdrs):
    """Return (cacheable, lifetime_seconds)."""
    hd = {k.lower(): v for k, v in hdrs}
    directives = [d.strip() for d in hd.get("cache-control", "").lower().split(",") if d.strip()]
    if "no-store" in directives or "private" in directives:
        return False, 0
    if "no-cache" in directives:
        return True, 0                       # store, but re-validate every time
    for d in directives:
        if d.startswith("max-age="):
            try:
                return True, max(0, int(d.split("=", 1)[1]))
            except ValueError:
                pass
    if "expires" in hd:
        try:
            exp = email.utils.parsedate_to_datetime(hd["expires"]).timestamp()
            return True, max(0, exp - time.time())
        except (TypeError, ValueError):
            return True, 0                   # invalid Expires = already expired
    return True, CONFIG["ttl"]


def maybe_store(url, resp):
    ok, life = freshness(resp["headers"])
    hd = {k.lower(): v for k, v in resp["headers"]}
    complete = ("content-length" not in hd) or (int(hd["content-length"]) == len(resp["body"]))
    with cache_lock:
        if resp["status"] != 200 or not ok or not complete:
            cache.pop(url, None)             # never keep a stale/uncacheable copy
            return
        cache[url] = {"status": 200, "reason": resp["reason"], "headers": resp["headers"],
                      "body": resp["body"], "stored": time.monotonic(), "lifetime": life,
                      "etag": hd.get("etag"), "lm": hd.get("last-modified")}


def send_response(csock, r, method, result, age=None):
    out = [f"HTTP/1.1 {r['status']} {r['reason']}"]
    for k, v in r["headers"]:
        kl = k.lower()
        if kl in HOP_BY_HOP:
            continue
        if kl == "content-length" and method != "HEAD":
            continue                         # we add our own below
        out.append(f"{k}: {v}")
    if method != "HEAD":
        out.append(f"Content-Length: {len(r['body'])}")
    out.append(f"X-Cache: {result}")
    if age is not None:
        out.append(f"Age: {int(age)}")
    out.append("Connection: close")
    raw = ("\r\n".join(out) + "\r\n\r\n").encode("iso-8859-1")
    payload = b"" if method == "HEAD" else r["body"]
    csock.sendall(raw + payload)
    return len(raw) + len(payload)


def serve_get(csock, url, host, port, path, fwd):
    # the proxy always works with full copies: drop the client's own conditional/range headers.
    fwd = [(k, v) for k, v in fwd
           if k.lower() not in ("if-none-match", "if-modified-since", "range", "if-range")]
    with cache_lock:
        entry = cache.get(url)

    if entry is not None:
        age = time.monotonic() - entry["stored"]
        if age < entry["lifetime"]:                                   # fresh -> HIT
            n = send_response(csock, entry, "GET", "HIT", age)
            log_line("GET", url, "HIT", entry["status"], n)
            return
        cond = []                                                     # stale -> conditional GET
        if entry["etag"]:
            cond.append(("If-None-Match", entry["etag"]))
        if entry["lm"]:
            cond.append(("If-Modified-Since", entry["lm"]))
        resp = fetch_origin("GET", host, port, path, fwd + cond)
        if resp["status"] == 304:
            names = {k.lower() for k, _ in resp["headers"]}
            with cache_lock:
                entry["stored"] = time.monotonic()
                if "cache-control" in names or "expires" in names:
                    entry["lifetime"] = freshness(resp["headers"])[1]
            n = send_response(csock, entry, "GET", "REVALIDATE_304")
            log_line("GET", url, "REVALIDATE_304", entry["status"], n)
            return
        result = "REVALIDATE_200" if resp["status"] == 200 else "MISS"
    else:
        resp = fetch_origin("GET", host, port, path, fwd)
        result = "MISS"

    maybe_store(url, resp)
    n = send_response(csock, resp, "GET", result)
    log_line("GET", url, result, resp["status"], n)


def handle_client(csock, caddr):
    try:
        csock.settimeout(30)
        csock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        head, body = read_head(csock)
        if head is None:
            return
        lines = head.decode("iso-8859-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            send_simple(csock, 400, "Bad Request", "Bad Request\n")
            return
        headers = parse_headers(lines[1:])
        hdict = {k.lower(): v for k, v in headers}

        u = urlsplit(target)
        if target.startswith("/") and u.path == "/__clear":           # admin: reset cache + log
            clear_all()
            send_simple(csock, 200, "OK", "Cache and log cleared\n")
            return

        if u.hostname:                                                # absolute URI (proxy request)
            host, port = u.hostname, (u.port or 80)
            path = (u.path or "/") + (("?" + u.query) if u.query else "")
        elif "host" in hdict:                                         # origin-form + Host header
            host, _, p = hdict["host"].partition(":")
            port = int(p) if p else 80
            path = target
        else:
            send_simple(csock, 400, "Bad Request", "Bad Request\n")
            return

        clen = int(hdict.get("content-length", 0))
        while len(body) < clen:
            chunk = csock.recv(BUFSZ)
            if not chunk:
                break
            body += chunk

        url = f"http://{host}:{port}{path}"
        fwd = [(k, v) for k, v in headers if k.lower() not in HOP_BY_HOP and k.lower() != "host"]

        if method == "GET":
            serve_get(csock, url, host, port, path, fwd)
        else:                                                         # POST, HEAD, others: never cached
            resp = fetch_origin(method, host, port, path, fwd, body)
            n = send_response(csock, resp, method, "BYPASS")
            log_line(method, url, "BYPASS", resp["status"], n)
    except (OSError, ValueError) as e:
        print("error:", e, flush=True)
        try:
            send_simple(csock, 502, "Bad Gateway", "Bad Gateway\n")
        except OSError:
            pass
    finally:
        csock.close()


def main():
    global LOGF
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Caching HTTP proxy")
    ap.add_argument("--port", type=int, default=8888)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--ttl", type=int, default=30, help="default freshness lifetime (s)")
    ap.add_argument("--log", default=os.path.join(here, "proxy.log"))
    ap.add_argument("--quiet", action="store_true", help="do not echo log lines to the screen")
    args = ap.parse_args()
    CONFIG["ttl"] = args.ttl
    CONFIG["quiet"] = args.quiet
    LOGF = open(args.log, "a", buffering=1)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.bind, args.port))
    srv.listen(128)
    print(f"Proxy on {args.bind}:{args.port} ttl={args.ttl}s log={args.log}", flush=True)
    try:
        while True:
            csock, caddr = srv.accept()
            threading.Thread(target=handle_client, args=(csock, caddr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
