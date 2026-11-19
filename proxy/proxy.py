#!/usr/bin/env python3
"""Caching HTTP proxy on plain sockets.
Persistent client connections (keep-alive) and a pool of persistent upstream connections.
Cache: TTL, conditional GET (If-None-Match / If-Modified-Since), request log.
Limits: chunked responses unsupported, no pipelining, only GET is cached."""
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
CONFIG = {"ttl": 30, "quiet": False, "upstream_ka": True, "idle": 15}
UP_IDLE_MAX = 3.0               

cache = {}                      
cache_lock = threading.Lock()
log_lock = threading.Lock()
pool = {}                       # (host, port) -> list of (socket, last_used)
pool_lock = threading.Lock()    # also protects STATS
STATS = {"upstream_connects": 0, "upstream_reused": 0}
LOGF = None


def log_line(method, url, result, status, nbytes):
    line = "\t".join([datetime.now().isoformat(timespec="milliseconds"),
                      method, url, result, str(status), str(nbytes)])
    with log_lock:
        LOGF.write(line + "\n")
    if not CONFIG["quiet"]:
        print(line, flush=True)


def bump(name):
    with pool_lock:
        STATS[name] += 1


def pool_get(host, port):
    now = time.monotonic()
    with pool_lock:
        lst = pool.get((host, port), [])
        while lst:
            s, last = lst.pop()
            if now - last <= UP_IDLE_MAX:
                return s
            s.close()
    return None


def pool_put(host, port, s):
    with pool_lock:
        pool.setdefault((host, port), []).append((s, time.monotonic()))


def pool_clear():
    with pool_lock:
        for lst in pool.values():
            for s, _ in lst:
                s.close()
        pool.clear()


def clear_all():
    with cache_lock:
        cache.clear()
    pool_clear()
    with pool_lock:
        for k in STATS:
            STATS[k] = 0
    with log_lock:
        LOGF.truncate(0)


def parse_headers(lines):
    out = []
    for line in lines:
        if ":" in line:
            k, v = line.split(":", 1)
            out.append((k.strip(), v.strip()))
    return out


def read_head(sock, data=b""):
    """Read until the blank line. Return (head_bytes, leftover) or (None, b'')."""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(BUFSZ)
        if not chunk:
            break
        data += chunk
    head, sep, rest = data.partition(b"\r\n\r\n")
    return (head, rest) if sep else (None, b"")


def send_simple(csock, code, reason, text, keep=False):
    body = text.encode()
    conn = "keep-alive" if keep else "close"
    csock.sendall((f"HTTP/1.1 {code} {reason}\r\nContent-Type: text/plain\r\n"
                   f"Content-Length: {len(body)}\r\nConnection: {conn}\r\n\r\n").encode() + body)


def read_response(us, method):
    """Read one response from the origin. Adds 'reusable' = connection may be kept."""
    head, rest = read_head(us)
    if head is None:
        raise OSError("bad response from origin")
    lines = head.decode("iso-8859-1").split("\r\n")
    parts = lines[0].split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise OSError("bad status line from origin")
    status = int(parts[1])
    reason = parts[2] if len(parts) > 2 else ""
    hdrs = parse_headers(lines[1:])
    hd = {k.lower(): v for k, v in hdrs}
    if "chunked" in hd.get("transfer-encoding", "").lower():
        raise OSError("chunked responses not supported")
    reusable = parts[0] == "HTTP/1.1" and "close" not in hd.get("connection", "").lower()
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
            reusable = False
    return {"status": status, "reason": reason, "headers": hdrs, "body": data,
            "reusable": reusable}


def fetch_origin(method, host, port, path, headers, body=b""):
    """One request to the origin, reusing a pooled connection when possible."""
    use_pool = CONFIG["upstream_ka"]
    out = (f"{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
           f"Connection: {'keep-alive' if use_pool else 'close'}\r\n")
    for k, v in headers:
        out += f"{k}: {v}\r\n"
    out += "\r\n"
    payload = out.encode("iso-8859-1") + body
    for attempt in (0, 1):
        us = pool_get(host, port) if (use_pool and attempt == 0) else None
        reused = us is not None
        if reused:
            bump("upstream_reused")
        else:
            us = socket.create_connection((host, port), timeout=10)
            us.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            bump("upstream_connects")
        try:
            us.sendall(payload)
            resp = read_response(us, method)
        except OSError:
            us.close()
            if reused and method in ("GET", "HEAD"):   
                continue
            raise
        if use_pool and resp["reusable"]:
            pool_put(host, port, us)
        else:
            us.close()
        return resp


def freshness(hdrs):
    """Return (cacheable, lifetime_seconds)."""
    hd = {k.lower(): v for k, v in hdrs}
    directives = [d.strip() for d in hd.get("cache-control", "").lower().split(",") if d.strip()]
    if "no-store" in directives or "private" in directives:
        return False, 0
    if "no-cache" in directives:
        return True, 0
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
            return True, 0
    return True, CONFIG["ttl"]


def maybe_store(url, resp):
    ok, life = freshness(resp["headers"])
    hd = {k.lower(): v for k, v in resp["headers"]}
    complete = ("content-length" not in hd) or (int(hd["content-length"]) == len(resp["body"]))
    with cache_lock:
        if resp["status"] != 200 or not ok or not complete:
            cache.pop(url, None)
            return
        cache[url] = {"status": 200, "reason": resp["reason"], "headers": resp["headers"],
                      "body": resp["body"], "stored": time.monotonic(), "lifetime": life,
                      "etag": hd.get("etag"), "lm": hd.get("last-modified")}


def send_response(csock, r, method, result, age=None, keep=False):
    out = [f"HTTP/1.1 {r['status']} {r['reason']}"]
    for k, v in r["headers"]:
        kl = k.lower()
        if kl in HOP_BY_HOP:
            continue
        if kl == "content-length" and method != "HEAD":
            continue
        out.append(f"{k}: {v}")
    if method != "HEAD":
        out.append(f"Content-Length: {len(r['body'])}")
    out.append(f"X-Cache: {result}")
    if age is not None:
        out.append(f"Age: {int(age)}")
    out.append("Connection: keep-alive" if keep else "Connection: close")
    raw = ("\r\n".join(out) + "\r\n\r\n").encode("iso-8859-1")
    payload = b"" if method == "HEAD" else r["body"]
    csock.sendall(raw + payload)
    return len(raw) + len(payload)


def serve_get(csock, url, host, port, path, fwd, keep):
    fwd = [(k, v) for k, v in fwd
           if k.lower() not in ("if-none-match", "if-modified-since", "range", "if-range")]
    with cache_lock:
        entry = cache.get(url)

    if entry is not None:
        age = time.monotonic() - entry["stored"]
        if age < entry["lifetime"]:                                   
            n = send_response(csock, entry, "GET", "HIT", age, keep)
            log_line("GET", url, "HIT", entry["status"], n)
            return
        cond = []                                                     
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
            n = send_response(csock, entry, "GET", "REVALIDATE_304", None, keep)
            log_line("GET", url, "REVALIDATE_304", entry["status"], n)
            return
        result = "REVALIDATE_200" if resp["status"] == 200 else "MISS"
    else:
        resp = fetch_origin("GET", host, port, path, fwd)
        result = "MISS"

    maybe_store(url, resp)
    n = send_response(csock, resp, "GET", result, None, keep)
    log_line("GET", url, result, resp["status"], n)


def handle_one(csock, head, rest):
    """Handle one request. Return (keep_alive, leftover_bytes)."""
    lines = head.decode("iso-8859-1").split("\r\n")
    try:
        method, target, version = lines[0].split(" ", 2)
    except ValueError:
        send_simple(csock, 400, "Bad Request", "Bad Request\n")
        return False, b""
    headers = parse_headers(lines[1:])
    hdict = {k.lower(): v for k, v in headers}
    tokens = (hdict.get("connection", "") + "," + hdict.get("proxy-connection", "")).lower()
    keep = ("close" not in tokens) if version == "HTTP/1.1" else ("keep-alive" in tokens)

    clen = int(hdict.get("content-length", 0))
    while len(rest) < clen:
        chunk = csock.recv(BUFSZ)
        if not chunk:
            break
        rest += chunk
    body, leftover = rest[:clen], rest[clen:]

    u = urlsplit(target)
    if target.startswith("/") and u.path == "/__clear":             
        clear_all()
        send_simple(csock, 200, "OK", "Cache, pool, stats and log cleared\n", keep)
        return keep, leftover
    if target.startswith("/") and u.path == "/__stats":              
        with pool_lock:
            txt = (f"upstream_connects={STATS['upstream_connects']} "
                   f"upstream_reused={STATS['upstream_reused']}\n")
        send_simple(csock, 200, "OK", txt, keep)
        return keep, leftover

    if u.hostname:                                                   
        host, port = u.hostname, (u.port or 80)
        path = (u.path or "/") + (("?" + u.query) if u.query else "")
    elif "host" in hdict:                                             
        host, _, p = hdict["host"].partition(":")
        port = int(p) if p else 80
        path = target
    else:
        send_simple(csock, 400, "Bad Request", "Bad Request\n")
        return False, b""

    url = f"http://{host}:{port}{path}"
    fwd = [(k, v) for k, v in headers if k.lower() not in HOP_BY_HOP and k.lower() != "host"]

    if method == "GET":
        serve_get(csock, url, host, port, path, fwd, keep)
    else:                                                            
        resp = fetch_origin(method, host, port, path, fwd, body)
        n = send_response(csock, resp, method, "BYPASS", None, keep)
        log_line(method, url, "BYPASS", resp["status"], n)
    return keep, leftover


def handle_client(csock, caddr):
    try:
        csock.settimeout(CONFIG["idle"])                             
        csock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        buf = b""
        while True:
            try:
                head, buf = read_head(csock, buf)
            except OSError:                                          
                break
            if head is None:
                break
            try:
                keep, buf = handle_one(csock, head, buf)
            except (OSError, ValueError) as e:
                print("error:", e, flush=True)
                try:
                    send_simple(csock, 502, "Bad Gateway", "Bad Gateway\n")
                except OSError:
                    pass
                break
            if not keep:
                break
    finally:
        csock.close()


def main():
    global LOGF
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Caching HTTP proxy")
    ap.add_argument("--port", type=int, default=8888)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--ttl", type=int, default=30, help="default freshness lifetime (s)")
    ap.add_argument("--idle", type=int, default=15, help="idle client keep-alive timeout (s)")
    ap.add_argument("--no-upstream-keepalive", action="store_true",
                    help="new TCP connection to the origin for every request")
    ap.add_argument("--log", default=os.path.join(here, "proxy.log"))
    ap.add_argument("--quiet", action="store_true", help="do not echo log lines to the screen")
    args = ap.parse_args()
    CONFIG["ttl"] = args.ttl
    CONFIG["quiet"] = args.quiet
    CONFIG["idle"] = args.idle
    CONFIG["upstream_ka"] = not args.no_upstream_keepalive
    LOGF = open(args.log, "a", buffering=1)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.bind, args.port))
    srv.listen(128)
    print(f"Proxy on {args.bind}:{args.port} ttl={args.ttl}s "
          f"upstream-keepalive={'on' if CONFIG['upstream_ka'] else 'off'} log={args.log}",
          flush=True)
    try:
        while True:
            csock, caddr = srv.accept()
            threading.Thread(target=handle_client, args=(csock, caddr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
