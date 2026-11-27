## Origin server details
- GET / returns index.html (200). GET /old.html returns 301 with Location: /index.html.
- POST to any path returns 200 with the text "Received N bytes".
- Unsupported methods return 405; malformed requests return 400.
- HTTP/1.1 is persistent by default. HTTP/1.0 is persistent only with "Connection: keep-alive" (ab -k).
- Idle keep-alive timeout: 5 s. Thread pool: 64 workers. Keep ab -c at or below the pool size.
- Flags: --port --bind --root --threads --timeout --no-keepalive --max-age N --quiet
- Server log (stdout), tab-separated: timestamp, client IP, method, path, status, body bytes.
- ETag format: "<mtime_ns hex>-<size hex>". It changes whenever a file is touched or edited.
