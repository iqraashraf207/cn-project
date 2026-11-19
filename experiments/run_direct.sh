#!/bin/bash
# Usage: sudo ./experiments/run_direct.sh [runs]     (default 5 runs per case)
# Needs: topology up, origin server running inside the origin namespace.
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
cd "$(dirname "$0")/.."
RUNS=${1:-5}
OUT=experiments/results/direct_full.csv
if [ -f "$OUT" ]; then echo "$OUT exists. Delete it first to rerun."; exit 1; fi
for RTT in 20 100 200; do
  ./topology/set_rtt.sh $RTT
  echo "--- RTT $RTT ms: ping check ---"
  ip netns exec client ping -c 5 -q 10.0.3.10 | tail -2
  for MODE in nonpersistent persistent; do
    echo "--- direct $MODE at $RTT ms ---"
    ip netns exec client python3 client/client.py --mode $MODE --runs $RUNS --rtt $RTT --label direct --csv $OUT
  done
done
./topology/set_rtt.sh 0
echo "Done. Results in $OUT"
