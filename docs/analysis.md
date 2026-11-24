# Analysis: measured results vs the textbook model

## 1. The textbook model

Kurose and Ross (Chapter 2) say that fetching one object over HTTP costs 1 RTT to set up the TCP connection plus 1 RTT for the request and response, with transmission time ignored. For the test page (1 base page + 20 objects = 21 requests, fetched one at a time):

- Non-persistent HTTP: 21 x 2 RTT = 42 RTT, with 21 TCP connections.
- Persistent HTTP without pipelining: 1 RTT (handshake) + 21 x 1 RTT = 22 RTT, with 1 TCP connection.

Predictions: 8.4 s vs 4.4 s at 200 ms, 4.2 s vs 2.2 s at 100 ms, and 0.84 s vs 0.44 s at 20 ms. All page-load experiments (direct and through the proxy), the cache hit ratio, the repeat visits and both ApacheBench benchmarks were run on one machine (Samiya's), a VirtualBox virtual machine on a laptop, with 5 runs per page-load case.

## 2. Non-persistent vs persistent (direct, no proxy)

| RTT (ms) | Case | Mean ± std dev (s) | Fastest run (s) | Model (s) | Mean vs model | Fastest run vs model |
|---|---|---|---|---|---|---|
| 20 | Non-persistent | 2.066 ± 0.805 | 0.955 | 0.840 | +145.9% | +13.7% |
| 20 | Persistent | 0.666 ± 0.195 | 0.537 | 0.440 | +51.5% | +22.0% |
| 100 | Non-persistent | 5.467 ± 0.501 | 4.947 | 4.200 | +30.2% | +17.8% |
| 100 | Persistent | 2.705 ± 0.444 | 2.416 | 2.200 | +22.9% | +9.8% |
| 200 | Non-persistent | 10.674 ± 0.841 | 9.430 | 8.400 | +27.1% | +12.3% |
| 200 | Persistent | 5.083 ± 0.348 | 4.777 | 4.400 | +15.5% | +8.6% |

- Both modes scale linearly with the RTT, and non-persistent HTTP is always much slower. The ratio non-persistent / persistent of the means is 3.10 at 20 ms, 2.02 at 100 ms and 2.10 at 200 ms (model: 1.91). Using the fastest run of each case, the ratios are 1.78, 2.05 and 1.97, close to the model.
- Persistence saved 1.40 s at 20 ms, 2.76 s at 100 ms and 5.59 s at 200 ms.
- Every measured mean is above the model: by 27% to 146% for non-persistent and 16% to 52% for persistent HTTP. The excess is largest at 20 ms, where the model value is only 0.44 to 0.84 s and a delay of a few hundred milliseconds changes the result a lot. It is also noisiest there: the standard deviation is 39% of the mean for non-persistent and 29% for persistent HTTP at 20 ms, but only 6.8% to 16.4% at 100 and 200 ms.
- The fastest run of each case, which is the run least disturbed by the virtual machine, is 8.6% to 22.0% above the model. The model ignores transmission and processing time, so a small positive difference is expected.
- Run-to-run variation is large relative to the differences between cases at 100 and 200 ms, so these results show the trend clearly (about a factor of 2 between the two modes, scaling with the RTT) but not precise percentages. An earlier run of the same direct experiment on the other team member's machine (kept in experiments/results/direct_full_iqra_machine.csv) gave different absolute times, which also shows that the absolute results depend on the host machine.

## 3. Effective RTT in the virtual machine

Ping with 20 samples per setting (docs/evidence/ping_effective_rtt.txt):

| Nominal RTT (ms) | min (ms) | avg (ms) | max (ms) | std dev (ms) | avg minus nominal (ms) |
|---|---|---|---|---|---|
| 20 | 20.985 | 44.323 | 298.561 | 61.051 | +24.3 (+122%) |
| 100 | 100.860 | 112.535 | 154.264 | 17.792 | +12.5 (+13%) |
| 200 | 201.692 | 250.959 | 465.750 | 68.067 | +51.0 (+25%) |

- The minimum RTT is within 1.0, 0.9 and 1.7 ms of the nominal value, so tc netem applies the intended delay.
- The average is above nominal by an amount that is not constant (24.3, 12.5 and 51.0 ms), and the maxima reach 299, 154 and 466 ms. The extra time therefore comes from occasional large delays in the virtual machine (most likely CPU scheduling of the VM and of the network namespaces), and not from a fixed cost per round trip. This is also why the standard deviation of the page-load times is so large at 20 ms.
- Python processing time cannot explain the excess. A page load from a warm proxy cache takes only 22 to 35 ms for all 21 requests (about 1 to 2 ms per request, including the client and the proxy), while the measured excess over the model is 11 to 108 ms per request (see docs/results_tables.md).

If the nominal RTT is replaced by the average RTT measured with ping in the same virtual machine, the model moves much closer to the measurements:

| Nominal RTT (ms) | Average ping (ms) | 42 x avg (s) | Measured non-persistent (s) | Difference | 22 x avg (s) | Measured persistent (s) | Difference |
|---|---|---|---|---|---|---|---|
| 20 | 44.3 | 1.862 | 2.066 | +11.0% | 0.975 | 0.666 | -31.7% |
| 100 | 112.5 | 4.726 | 5.467 | +15.7% | 2.476 | 2.705 | +9.3% |
| 200 | 251.0 | 10.540 | 10.674 | +1.3% | 5.521 | 5.083 | -7.9% |

At 100 and 200 ms the prediction with the measured RTT is within 16% of the measurement (with the nominal RTT the differences were +15% to +30%). At 20 ms the average ping is dominated by a few spikes, so the persistent prediction is 32% too high. The ping sample (20 pings per setting) was taken at a different time from the page loads, so it supports a qualitative explanation (a jittery, slower effective RTT) but is not a precise correction.

## 4. TCP connections per page

The client opened 21 connections in non-persistent mode and 1 in persistent mode, in every run and at every RTT. This was confirmed with two independent methods: counting SYN packets in the captures (21 and 1 SYN packets in captures/connections_nonpersistent_rtt100.pcap and captures/connections_persistent_rtt100.pcap), and sampling `ss` (1 distinct client port for the persistent load; 20 for the non-persistent load, because one very short-lived connection fell between two 50 ms samples, so the SYN count is the authoritative one). This matches the textbook model exactly.

## 5. The caching proxy

| RTT (ms) | Direct persistent (s) | Proxy, empty cache (s) | Difference | Proxy, warm cache (s) | Warm speed-up vs direct persistent |
|---|---|---|---|---|---|
| 20 | 0.666 ± 0.195 | 1.302 ± 0.297 | +95.4% | 0.022 ± 0.011 | 30x |
| 100 | 2.705 ± 0.444 | 2.900 ± 0.341 | +7.2% | 0.035 ± 0.025 | 77x |
| 200 | 5.083 ± 0.348 | 5.267 ± 0.326 | +3.6% | 0.025 ± 0.013 | 206x |

- **Empty cache.** The proxy keeps one persistent connection to the origin, so a page with an empty cache costs the same 22 RTT as direct persistent HTTP, and the measurements agree: at 100 and 200 ms the proxy is only 7.2% and 3.6% slower, and the difference (0.195 s and 0.184 s) is smaller than the run-to-run standard deviation (0.33 to 0.44 s), so it is not significant. That is about 9 ms per request, far more than the 1 to 2 ms the proxy needs for a cache hit, so it is noise and not proxy processing. At 20 ms the proxy is 95% slower (0.636 s, about 30 ms per request). This is larger than the standard error of the difference (about 0.16 s), but 20 ms is the noisiest setting and we cannot explain this value with the data we have. More runs at 20 ms would be needed to settle it.
- **Warm cache.** The page loads in 22 to 35 ms at every RTT, and the three values do not depend on the RTT (they differ by less than their standard deviations). No packet crosses the delayed link, because the client only talks to the proxy on LAN-A. This is 30 to 206 times faster than direct persistent HTTP and removes 96.7% to 99.5% of the load time.
- **What the upstream connection pool saves.** With the pool switched off (--no-upstream-keepalive, 3 runs at 100 ms in a separate session) every cache miss opens a new connection to the origin (upstream_connects = 21, upstream_reused = 0) and the page took 4.765 s (std dev 0.063 s). That is 13.5% above the 42 RTT model value of 4.2 s, and 1.865 s (39%) slower than the same page with the pool (2.900 s, 22 RTT). The measured ratio of 1.64 is a little below 42/22 = 1.91, again because of the extra time in the virtual machine.

## 6. Conditional GET and repeat visits (RTT 100 ms, TTL 5 s, one run per visit)

| Visit | Load time (s) | Proxy log outcomes |
|---|---|---|
| 1: empty cache | 3.035 | 21 MISS |
| 2: fresh entries | 0.011 | 21 HIT |
| 3: stale, nothing changed | 3.360 | 21 REVALIDATE_304 |
| 4: stale, 5 objects changed | 3.231 | 5 REVALIDATE_200, 16 REVALIDATE_304 |

- Visit 3 took 3.360 s, not near zero. Each of the 21 conditional GETs still crosses the delayed link and costs 1 RTT, so a revalidation is about as slow as a cache miss (3.035 s). The saving of a 304 is bytes, not time. The 3 slow visits differ by less than the standard deviation of the empty-cache case at 100 ms (0.34 s), so their differences are not significant (one run each).
- Visit 4 behaves as expected: the 5 objects that were touched (obj01 to obj05) returned 200 with a new ETag and were replaced, and the other 16 returned 304.
- A 304 response is 213 bytes (headers only), while a full 200 is 10,506 bytes (266 bytes of headers + 10,240 bytes of body). One 304 therefore saves 10,293 bytes (98% of the response). The 37 REVALIDATE_304 responses of this experiment saved 380,841 bytes (about 372 KiB).

## 7. Cache hit ratio

Hit ratio = (HIT + REVALIDATE_304) / GET requests.

- Five consecutive page loads with a long TTL (3600 s): the first load is 21 MISS and the other four are 21 HIT each, so the ratio is 84 / 105 = 0.800.
- Repeat-visit experiment (4 visits, 84 GET requests: 21 MISS, 21 HIT, 37 REVALIDATE_304, 5 REVALIDATE_200): (21 + 37) / 84 = 0.690.

## 8. Throughput (ApacheBench)

Both the origin server and the proxy were benchmarked on the same machine (Samiya's) at RTT 0, with 3000 requests per run and 3 runs per case, always for the same 10 KB object (the proxy only answered cache hits). Medians and ranges are reported because the runs of the same case varied by up to about 4 times on the virtualised host (mostly in the cases without keep-alive).

| Target | Concurrency | No keep-alive: median (min-max) req/s | Keep-alive (-k): median (min-max) req/s | Keep-alive speed-up |
|---|---|---|---|---|
| Origin server | 1 | 513 (472-1128) | 3289 (2806-4034) | 6.4x |
| Origin server | 10 | 420 (364-1430) | 1412 (1145-2393) | 3.4x |
| Origin server | 50 | 1469 (399-1512) | 6319 (3261-6670) | 4.3x |
| Caching proxy | 1 | 480 (360-566) | 4032 (1824-5179) | 8.4x |
| Caching proxy | 10 | 586 (515-1404) | 5932 (4158-6013) | 10.1x |
| Caching proxy | 50 | 557 (536-1538) | 1733 (1702-1770) | 3.1x |

- Keep-alive raised the throughput by a factor of 3.1 to 10.1 in every case, because no new TCP connection and handshake is needed for each request.
- No error responses were recorded in any run (Non-2xx responses = 0 in all rows), so all requests were normal 200 responses.
- The proxy was faster than the origin with keep-alive at concurrency 1 (1.2 times) and 10 (4.2 times) and slower at concurrency 50 (the origin was 3.6 times faster). The ordering is not consistent and the runs vary a lot, so this comparison is inconclusive; no result in this table should be read as more precise than a factor of about 2 to 4. The throughput does not grow steadily with the concurrency either, which is expected when many Python threads share one interpreter lock (GIL) on a virtual machine with few CPUs.
- The concurrency was kept at or below the 64 worker threads of the origin server, because a persistent connection occupies one worker for as long as it stays open.

## 9. Limitations

- The measured page-load times are 15% to 146% above the model (8.6% to 22% for the fastest run of each case). The explanation supported by our data is jitter in the virtual machine (ping maxima of 299 to 466 ms, section 3), together with the processing and transmission time that the model ignores. The trend (a factor of about 2 between non-persistent and persistent HTTP, linear growth with the RTT, 21 vs 1 connections) agrees with the textbook.
- Only 5 runs per page-load case were made, so the means have a large uncertainty at 20 ms (standard deviation up to 0.8 s) and the 20 ms results should be read with caution.
- The proxy was measured against direct persistent HTTP on the same machine. At 100 and 200 ms the difference is not significant; at 20 ms the cause of the larger difference is unresolved.
- The proxy does not support chunked responses, pipelining, range requests or HTTPS. Simultaneous first requests for the same URL can all be misses (no request coalescing).
- The repeat-visit experiment used one run per visit, so its load times show the pattern but have no error estimate.
- Optional extras of the proposal were not done: packet loss with tc netem loss, bandwidth limits with tc tbf, and parallel connections.
