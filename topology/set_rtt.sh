#!/bin/bash
# Usage: sudo ./topology/set_rtt.sh <RTT_ms>   (0 removes delay)
# half of the RTT is applied on each side of the transit link
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
if [ -z "$1" ]; then echo "Usage: sudo $0 <RTT_ms>"; exit 1; fi
RTT=$1
HALF=$((RTT / 2))
if [ "$RTT" -eq 0 ]; then
  ip netns exec r1 tc qdisc del dev veth-r1 root 2>/dev/null || true
  ip netns exec r2 tc qdisc del dev veth-r2 root 2>/dev/null || true
  echo "Delay removed."
else
  ip netns exec r1 tc qdisc replace dev veth-r1 root netem delay ${HALF}ms
  ip netns exec r2 tc qdisc replace dev veth-r2 root netem delay ${HALF}ms
  echo "Set ${HALF}ms on each side (RTT ~ ${RTT}ms). Verify with ping."
fi
