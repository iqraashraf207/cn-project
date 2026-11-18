- Cache key: the full absolute URL (for example http://10.0.3.10:8080/obj01.dat).

-  What gets stored per entry: status line, headers, body, time stored, ETag, Last-Modified.

- Freshness rule: fresh if age < TTL (default 30 s, configurable with --ttl), unless the origin sent Cache-Control: max-age or Expires.

- Stale rule: send a conditional GET with If-None-Match (if ETag stored) and If-Modified-Since (if Last-Modified stored). A 304 from the origin means update the stored time and serve the cached body. A 200 means replace the entry.

- Never cache: POST, and any response that isn’t 200.


- Only GET is cached. HEAD, POST and everything else are forwarded (RESULT = BYPASS).

- Only 200 responses are stored. A non-200 revalidation response removes the old copy (logged MISS).

- A fresh entry (age < lifetime) is served directly (HIT). The lifetime is Cache-Control max-age, else Expires, else --ttl.

- A stale entry triggers a conditional GET with If-None-Match (ETag) and If-Modified-Since (Last-Modified).
304 = REVALIDATE_304 (timer reset, cached body served). 200 = REVALIDATE_200 (entry replaced).

- The client's own conditional/range headers are dropped, so the client always receives a full 200.

- Responses carry X-Cache: HIT / MISS / REVALIDATE_304 / REVALIDATE_200 / BYPASS for easy checking.

- Admin: GET http://<proxy>:8888/__clear empties the cache and the log (used between experiment runs).
