# Evidence index

## Topology and routing (docs/evidence/)
| File | What it shows |
|---|---|
| r1_addr.txt, r2_addr.txt | Interface addresses of both routers |
| r1_routes.txt, r2_routes.txt | Static routes (R1 to 10.0.3.0/24 via 10.0.12.2; R2 to 10.0.1.0/24 via 10.0.12.1) |
| r1_bridge.txt | Bridge br0 ports on R1 (LAN-A) |
| traceroute_client_to_origin.txt | Three hops: 10.0.1.1, 10.0.12.2, 10.0.3.10 |
| ping_rtt100.txt | 10 pings across the netem link set to 100 ms |
| ping_effective_rtt.txt | 20 pings at each of 20, 100 and 200 ms (min, avg, max), used to explain the measured excess |
| ping_client_proxy.txt | Client to proxy (no delay) compared with client to origin (delayed) |

## Packet captures (captures/, open in Wireshark)
| File | Exchange |
|---|---|
| 01_tcp_handshake.pcapng | TCP three-way handshake and one request (client side) |
| 02_get_200.pcapng | GET /index.html answered with 200 and headers |
| 03_connection_reuse.pcapng | Full page load on one persistent connection (1 SYN, 21 requests) |
| 03b_nonpersistent_21_connections.pcapng | Same page, new connection per object (21 SYNs) |
| 03c_persistent_1_connection.pcapng | Persistent page load (1 SYN), converted from the Day 4 capture |
| 04_conditional_get_304.pcapng | Proxy revalidation: If-None-Match / If-Modified-Since and 304 (both legs) |
| 05_proxy_cache_hit.pcapng | Proxy cache hit: no packet to the origin |
| connections_*.pcap | Captures used for SYN counting (21 vs 1) |

## Annotated screenshots (docs/evidence/screenshots/)
| File | Shows |
|---|---|
| s1_tcp_handshake.png | SYN, SYN-ACK, ACK, addresses, ports, about 100 ms gap |
| s2_get_200.png | Request and 200 response headers |
| s3_connection_reuse.png | 21 requests on the same TCP stream |
| s4_one_syn.png, s4b_21_syns.png | 1 SYN (persistent) vs 21 SYNs (non-persistent) |
| s5_conversations.png | One TCP conversation |
| s6_proxy_to_origin_conditional.png | Conditional GET sent by the proxy |
| s7_origin_304.png | 304 with no body |
| s8_proxy_to_client.png | Proxy answer to the client, X-Cache: REVALIDATE_304 |
| s9_two_legs_overview.png | Client-proxy leg and proxy-origin leg |
| s10_cache_hit.png, s10b_no_origin_traffic.png | Cache hit with zero origin packets |

## Results (experiments/results/)
| File | Content |
|---|---|
| direct_full.csv, proxy_full.csv | Page-load matrix, 5 runs per case at 20, 100 and 200 ms |
| direct_full_iqra_machine.csv | Earlier direct run on a second machine, kept for comparison |
| hitratio.csv, hitratio_proxy.log | 5 consecutive page loads and the proxy log (ratio 0.800) |
| revisit.csv, revisit_proxy.log | Four repeat visits and the proxy log (ratio 0.690) |
| ab_server.csv, ab_proxy.csv | ApacheBench runs (3 per case), with an error-response column |
| summary_*.csv | Summaries made by summarize.py |

## Other evidence
| File | Content |
|---|---|
| ss_samples_*.txt | Samples of `ss` output used to count connections |
| revisit_output.txt | Output of the repeat-visit experiment, including bytes saved by 304 |
| ../architecture.png | Architecture diagram |
| ../figures/fig1 to fig7 | Figures generated from the results |
