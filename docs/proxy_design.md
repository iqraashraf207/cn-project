1. Cache key: the full absolute URL (for example http://10.0.3.10:8080/obj01.dat).

2. What gets stored per entry: status line, headers, body, time stored, ETag, Last-Modified.

3. Freshness rule: fresh if age < TTL (default 30 s, configurable with --ttl), unless the origin sent Cache-Control: max-age or Expires.

4. Stale rule: send a conditional GET with If-None-Match (if ETag stored) and If-Modified-Since (if Last-Modified stored). A 304 from the origin means update the stored time and serve the cached body. A 200 means replace the entry.

5. Never cache: POST, and any response that isn’t 200.
