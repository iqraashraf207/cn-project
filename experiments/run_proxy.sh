#!/bin/bash
# Usage: sudo ./experiments/run_proxy.sh [runs]     (default 5 runs per case)
# Needs: topology up, origin server running (origin ns), proxy running (proxy ns) with --ttl 3600.
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
cd "$(dirname "$0")/.."
RUNS=${1:-5}
OUT=experiments/results/proxy_full.csv
PX=10.0.1.20:8888
if [ -f "$OUT" ]; then echo "$OUT exists. Delete it first to rerun."; exit 1; fi
for RTT in 20 100 200; do
  ./topology/set_rtt.sh $RTT
  echo "--- RTT $RTT ms: ping check (origin, then proxy) ---"
  ip netns exec client ping -c 5 -q 10.0.3.10 | tail -2
  ip netns exec client ping -c 3 -q 10.0.1.20 | tail -2
  echo "--- proxy_empty at $RTT ms (cache emptied before every run) ---"
  ip netns exec client python3 client/client.py --mode persistent --proxy $PX --clear-proxy --runs $RUNS --rtt $RTT --label proxy_empty --csv $OUT
  echo "--- warming the cache (this run is not recorded) ---"
  ip netns exec client curl -s http://$PX/__clear
  ip netns exec client python3 client/client.py --mode persistent --proxy $PX --runs 1 --rtt $RTT --label warmup
  echo "--- proxy_warm at $RTT ms ---"
  ip netns exec client python3 client/client.py --mode persistent --proxy $PX --runs $RUNS --rtt $RTT --label proxy_warm --csv $OUT
done
./topology/set_rtt.sh 0
echo "Done. Results in $OUT"
