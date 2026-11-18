#!/usr/bin/env python3
"""Day 1 skeleton: forwards requests to the origin. No caching yet."""
import argparse
import socket
import threading
from urllib.parse import urlsplit

BUFSZ = 65536
HOP_BY_HOP = {"connection", "proxy-connection", "keep-alive", "te",
              "trailer", "transfer-encoding", "upgrade"}


def read_until_headers_end(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(BUFSZ)
        if not chunk:
            break
        data += chunk
    return data


def send_error(csock, code, text):
    body = f"{code} {text}\n".encode()
    resp = (f"HTTP/1.1 {code} {text}\r\nContent-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n").encode() + body
    csock.sendall(resp)


def handle_client(csock, caddr):
    try:
        raw = read_until_headers_end(csock)
        if not raw:
            return
        head, _, body = raw.partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            send_error(csock, 400, "Bad Request")
            return

        headers = []
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers.append((k.strip(), v.strip()))
        hdict = {k.lower(): v for k, v in headers}

        #work out the origin host/port/path
        u = urlsplit(target)
        if u.hostname:                      #absolute URI (normal proxy request)
            host, port = u.hostname, (u.port or 80)
            path = (u.path or "/") + (("?" + u.query) if u.query else "")
        elif "host" in hdict:               # origin-form + Host header
            hv = hdict["host"]
            host, _, p = hv.partition(":")
            port = int(p) if p else 80
            path = target
        else:
            send_error(csock, 400, "Bad Request")
            return

        # Read the rest of the body if there is one (POST)
        clen = int(hdict.get("content-length", 0))
        while len(body) < clen:
            chunk = csock.recv(BUFSZ)
            if not chunk:
                break
            body += chunk

        # Build upstream request
        out = f"{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n"
        for k, v in headers:
            if k.lower() not in HOP_BY_HOP and k.lower() != "host":
                out += f"{k}: {v}\r\n"
        out += "\r\n"

        try:
            usock = socket.create_connection((host, port), timeout=10)
        except OSError:
            send_error(csock, 502, "Bad Gateway")
            return
        with usock:
            usock.sendall(out.encode("iso-8859-1") + body)
            total = 0
            while True:
                chunk = usock.recv(BUFSZ)
                if not chunk:
                    break
                csock.sendall(chunk)
                total += len(chunk)
        print(f"[{caddr[0]}] {method} {target} -> relayed {total} bytes", flush=True)
    except Exception as e:
        print("error:", e, flush=True)
    finally:
        csock.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8888)
    ap.add_argument("--bind", default="0.0.0.0")
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.bind, args.port))
    srv.listen(128)
    print(f"Proxy listening on {args.bind}:{args.port}", flush=True)
    while True:
        csock, caddr = srv.accept()
        threading.Thread(target=handle_client, args=(csock, caddr), daemon=True).start()


if __name__ == "__main__":
    main()
