---
title: "HTTP/1.1 Web Server and Caching Proxy from Sockets: Persistent Connections and Conditional GET"
subtitle: "Computer Networks: Final Project Report"
author: "Iqra Ashraf (24K-0952), Samiya Khan (24K-0768), Aseelah Masood (24K-0881)"
date: "November 2026"
---

# Abstract {-}

This project builds an HTTP/1.1 web server and a caching proxy from plain TCP sockets in Python and measures how persistent connections and caching change page load time. Both run on a routed topology of five Linux network namespaces (two routers, three subnets) with delay added by tc netem at round-trip times of 20, 100 and 200 ms. A test page of 21 requests was loaded one request at a time in four ways. Opening a new connection for every object needed 21 TCP connections and took about twice as long as one persistent connection at 100 and 200 ms (5.47 s against 2.71 s at 100 ms), in line with the textbook ratio of 1.91. A warm proxy cache loaded the page in 22 to 35 ms at every delay, because no packet crossed the delayed link. A conditional GET answered with 304 needed 213 bytes instead of 10,506 bytes for a full response. The measured times were 15% to 30% above the textbook model at 100 and 200 ms, mostly because of timing jitter in the virtual machine, which we measured with ping and discuss in the report.
