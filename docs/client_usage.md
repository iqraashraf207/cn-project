# Client usage (client/client.py)

Loads index.html, then the 20 embedded objects one at a time. Measures load time (first connect to last byte
of the last object) and counts TCP connections opened.

    python3 client/client.py --mode persistent|nonpersistent [--url URL] [--proxy HOST:PORT]
                             [--runs N] [--clear-proxy] [--label TEXT] [--rtt MS] [--csv FILE]

- Default URL: http://10.0.3.10:8080/index.html (origin).
- --proxy 10.0.1.20:8888 sends absolute-URI requests to the proxy instead.
- --clear-proxy empties the proxy cache (not timed) before every run (for the "empty cache" case).
- Run inside the client namespace: sudo ip netns exec client python3 client/client.py ...
- Output per run: load_time, connections, requests, bytes, all_ok. CSV columns:
  label, mode, proxy, rtt_ms, run, load_time_s, connections, requests, bytes, all_ok.
- Expected results (textbook): non-persistent 42 RTT / 21 connections, persistent 22 RTT / 1 connection.
