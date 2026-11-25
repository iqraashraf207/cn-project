# Topology description

Everything runs on one laptop using Linux network namespaces: client, proxy, r1, r2 and origin. LAN-A (10.0.1.0/24) has three devices (R1, client, proxy), so a Linux bridge (br0) inside R1 joins them. LAN-B (10.0.12.0/30) is the transit link between R1 and R2. LAN-C (10.0.3.0/24) joins R2 and the origin. The routers have ip_forward = 1 and static routes only.

## Routing evidence

R1 routing table:

```
10.0.1.0/24 dev br0 proto kernel scope link src 10.0.1.1 
10.0.3.0/24 via 10.0.12.2 dev veth-r1 
10.0.12.0/30 dev veth-r1 proto kernel scope link src 10.0.12.1 
```

R2 routing table:

```
10.0.1.0/24 via 10.0.12.1 dev veth-r2 
10.0.3.0/24 dev veth-r2o proto kernel scope link src 10.0.3.1 
10.0.12.0/30 dev veth-r2 proto kernel scope link src 10.0.12.2 
```

Traceroute from the client to the origin:

```
traceroute to 10.0.3.10 (10.0.3.10), 30 hops max, 60 byte packets
 1  10.0.1.1  4.434 ms  0.011 ms  0.004 ms
 2  10.0.12.2  0.020 ms  0.003 ms  0.692 ms
 3  10.0.3.10  0.032 ms  0.004 ms  0.008 ms
```

Hop 1 is R1 (10.0.1.1), hop 2 is R2 (10.0.12.2) and hop 3 is the origin (10.0.3.10), so every packet between the client side and the server side crosses both routers.

## Delay

tc netem delay is set on veth-r1 and veth-r2, half of the RTT on each side, because netem delays packets in one direction only. The resulting RTT was checked with ping from the client to the origin (20 pings per setting, measured on the machine used for the page-load experiments):

| Nominal RTT (ms) | min (ms) | avg (ms) | max (ms) |
|---|---|---|---|
| 20 | 20.985 | 44.323 | 298.561 |
| 100 | 100.860 | 112.535 | 154.264 |
| 200 | 201.692 | 250.959 | 465.750 |

The minimum RTT is within 1.0, 0.9 and 1.7 ms of the nominal value, so the delay is applied as intended. The average and the maximum are higher because the virtual machine adds occasional large delays on top of the netem delay (CPU scheduling of the VM and of the namespaces); this is discussed in docs/analysis.md. Full output: docs/evidence/ping_effective_rtt.txt.

The path from the client to the proxy stays inside LAN-A and has no added delay:

```
== client -> proxy (inside LAN-A, delay set to 100 ms on the transit link)
rtt min/avg/max/mdev = 0.075/0.117/0.356/0.080 ms
== client -> origin (crosses the delayed link)
rtt min/avg/max/mdev = 101.842/129.792/275.268/50.930 ms
```

## Direct mode and proxy mode

In direct mode the client talks to the origin across the delayed link. In proxy mode the client talks to the proxy inside LAN-A (no added delay) and only the proxy-to-origin leg crosses the delayed link.
