#!/bin/bash
# Usage: sudo ./experiments/run_ab.sh server|proxy
# Needs: topology up, origin server running. For 'proxy' also the proxy running (use --ttl 3600).
# Runs ab from the client namespace at RTT 0 (so the result is server/proxy speed, not delay).
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
cd "$(dirname "$0")/.."
TARGET=$1
N=${N:-3000}
REPEATS=${REPEATS:-3}
case "$TARGET" in
  server) XFLAG="" ;;
  proxy)  XFLAG="-X 10.0.1.20:8888" ;;
  *) echo "Usage: sudo $0 server|proxy"; exit 1 ;;
esac
URL=http://10.0.3.10:8080/obj01.dat
OUT=experiments/results/ab_$TARGET.csv
if [ -f "$OUT" ]; then echo "$OUT exists. Delete it first to rerun."; exit 1; fi

./topology/set_rtt.sh 0 > /dev/null
if [ "$TARGET" = proxy ]; then
  ip netns exec client curl -s http://10.0.1.20:8888/__clear > /dev/null
  ip netns exec client curl -s -o /dev/null -x http://10.0.1.20:8888 $URL   # warm the cache
fi

echo "target,keepalive,concurrency,run,requests_per_sec,time_per_request_ms,failed,keepalive_requests,non2xx" > $OUT
for C in 1 10 50; do
  for KA in no yes; do
    KFLAG=""
    [ "$KA" = yes ] && KFLAG="-k"
    for R in $(seq 1 $REPEATS); do
      RES=$(ip netns exec client ab -q -n $N -c $C $KFLAG $XFLAG $URL 2>&1)
      RPS=$(echo "$RES" | awk '/^Requests per second/ {print $4}')
      TPR=$(echo "$RES" | awk '/^Time per request/ && /\(mean\)/ {print $4}')
      FAIL=$(echo "$RES" | awk '/^Failed requests/ {print $3}')
      KAR=$(echo "$RES" | awk '/^Keep-Alive requests/ {print $3}')
      N2=$(echo "$RES" | awk '/^Non-2xx responses/ {print $3}')
      echo "$TARGET,$KA,$C,$R,${RPS:-NA},${TPR:-NA},${FAIL:-NA},${KAR:-0},${N2:-0}" | tee -a $OUT
      sleep 2
    done
  done
done
echo "Done. Results in $OUT"
