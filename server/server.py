#!/usr/bin/env python3
"""HTTP/1.1 origin server on plain TCP sockets.
Methods: GET, HEAD, POST.  Status: 200, 301, 304, 404 (+400, 405, 500).
Features: Content-Length, keep-alive, conditional GET (ETag / If-Modified-Since), thread pool."""
import argparse
import email.utils
import mimetypes
import os
import queue
import socket
import threading
from datetime import datetime
from urllib.parse import unquote, urlsplit

REASONS = {200: "OK", 301: "Moved Permanently", 304: "Not Modified",
           400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
           500: "Internal Server Error"}
REDIRECTS = {"/old.html": "/index.html"}
MAX_HEADERS = 100
log_lock = threading.Lock()


def log(args, client, method, path, status, nbytes):
    if args.quiet:
        return
    stamp = datetime.now().isoformat(timespec="milliseconds")
    with log_lock:
        print(f"{stamp}\t{client}\t{method}\t{path}\t{status}\t{nbytes}", flush=True)


def read_request(rfile):
    """Return (method, target, version, headers, body), or None if the client closed."""
    line = rfile.readline(65537)
    while line in (b"\r\n", b"\n"):          # ignore stray blank lines
        line = rfile.readline(65537)
    if not line:
        return None
    try:
        method, target, version = line.decode("iso-8859-1").strip().split(" ")
    except ValueError:
        raise ValueError("bad request line")
    headers = {}
    for _ in range(MAX_HEADERS):
        h = rfile.readline(65537)
        if h in (b"\r\n", b"\n", b""):
            break
        k, sep, v = h.decode("iso-8859-1").partition(":")
        if not sep:
            raise ValueError("bad header")
        headers[k.strip().lower()] = v.strip()
    else:
        raise ValueError("too many headers")
    body = b""
    cl = headers.get("content-length")
    if cl:
        if not cl.isdigit():
            raise ValueError("bad content-length")
        body = rfile.read(int(cl))
    return method, target, version, headers, body


def make_response(status, headers, body=b"", head_only=False):
    lines = [f"HTTP/1.1 {status} {REASONS[status]}"]
    lines += [f"{k}: {v}" for k, v in headers]
    raw = ("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1")
    return raw if head_only else raw + body


def handle_request(args, root, req, client):
    """Return (response_bytes, keep_alive)."""
    method, target, version, h, body = req
    tokens = h.get("connection", "").lower()
    if version == "HTTP/1.1":
        keep = "close" not in tokens                 # HTTP/1.1: persistent by default
    else:
        keep = "keep-alive" in tokens                # HTTP/1.0: only if asked (ab -k)
    if args.no_keepalive:
        keep = False

    base = [("Date", email.utils.formatdate(usegmt=True)), ("Server", "CN-Origin/1.0")]
    if keep:
        base += [("Connection", "keep-alive"), ("Keep-Alive", f"timeout={args.timeout}")]
    else:
        base += [("Connection", "close")]

    path = unquote(urlsplit(target).path) or "/"

    def reply(status, extra=(), payload=b""):
        hdrs = base + list(extra)
        if status != 304:
            hdrs.append(("Content-Length", str(len(payload))))
        head_only = (method == "HEAD") or status == 304
        log(args, client, method, path, status, 0 if head_only else len(payload))
        return make_response(status, hdrs, payload, head_only), keep

    if method not in ("GET", "HEAD", "POST"):
        return reply(405, [("Allow", "GET, HEAD, POST"), ("Content-Type", "text/plain")],
                     b"405 Method Not Allowed\n")

    if method == "POST":
        return reply(200, [("Content-Type", "text/plain")],
                     f"Received {len(body)} bytes\n".encode())

    if path in REDIRECTS:
        return reply(301, [("Location", REDIRECTS[path]), ("Content-Type", "text/plain")],
                     b"Moved Permanently\n")

    rel = "index.html" if path == "/" else path.lstrip("/")
    full = os.path.realpath(os.path.join(root, rel))
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
        return reply(404, [("Content-Type", "text/plain")], b"404 Not Found\n")

    st = os.stat(full)
    etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
    last_mod = email.utils.formatdate(st.st_mtime, usegmt=True)
    validators = [("ETag", etag), ("Last-Modified", last_mod)]
    if args.max_age is not None:
        validators.append(("Cache-Control", f"max-age={args.max_age}"))

    inm = h.get("if-none-match")
    ims = h.get("if-modified-since")
    not_modified = False
    if inm is not None:                               # If-None-Match wins over If-Modified-Since
        tags = [t.strip() for t in inm.split(",")]
        tags = [t[2:] if t.startswith("W/") else t for t in tags]
        not_modified = ("*" in tags) or (etag in tags)
    elif ims is not None:
        try:
            t = email.utils.parsedate_to_datetime(ims).timestamp()
            not_modified = int(st.st_mtime) <= int(t)
        except (TypeError, ValueError):
            pass
    if not_modified:
        return reply(304, validators)

    with open(full, "rb") as f:
        data = f.read()
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    return reply(200, [("Content-Type", ctype)] + validators, data)


def serve_connection(args, root, conn, addr):
    rfile = None
    try:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        conn.settimeout(args.timeout)                # idle keep-alive timeout
        rfile = conn.makefile("rb")
        while True:
            try:
                req = read_request(rfile)
            except ValueError:
                conn.sendall(make_response(400, [("Content-Length", "0"), ("Connection", "close")]))
                break
            if req is None:
                break
            try:
                resp, keep = handle_request(args, root, req, addr[0])
            except Exception:
                resp = make_response(500, [("Content-Length", "0"), ("Connection", "close")])
                keep = False
            conn.sendall(resp)
            if not keep:
                break
    except OSError:                                   # timeout, reset, broken pipe
        pass
    finally:
        if rfile:
            rfile.close()
        conn.close()


def worker(q, args, root):
    while True:
        conn, addr = q.get()
        serve_connection(args, root, conn, addr)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="HTTP/1.1 origin server")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--root", default=os.path.join(here, "www"))
    ap.add_argument("--threads", type=int, default=64, help="thread pool size")
    ap.add_argument("--timeout", type=int, default=5, help="idle keep-alive timeout (s)")
    ap.add_argument("--no-keepalive", action="store_true", help="always Connection: close")
    ap.add_argument("--max-age", type=int, default=None, help="add Cache-Control: max-age=N")
    ap.add_argument("--quiet", action="store_true", help="no per-request log lines")
    args = ap.parse_args()
    root = os.path.realpath(args.root)

    q = queue.Queue()
    for _ in range(args.threads):
        threading.Thread(target=worker, args=(q, args, root), daemon=True).start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.bind, args.port))
    srv.listen(128)
    print(f"Origin server on {args.bind}:{args.port} root={root} threads={args.threads} "
          f"keep-alive={'off' if args.no_keepalive else 'on'}", flush=True)
    try:
        while True:
            conn, addr = srv.accept()
            q.put((conn, addr))
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
