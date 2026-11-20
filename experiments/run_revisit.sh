#!/bin/bash
# Usage: sudo ./experiments/run_revisit.sh
# Needs: topology up, origin server running, proxy running with --ttl 5 --quiet.
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
cd "$(dirname "$0")/.."
RTT=100
PX=10.0.1.20:8888
OUT=experiments/results/revisit.csv
if [ -f "$OUT" ]; then echo "$OUT exists. Delete it first to rerun."; exit 1; fi
C="ip netns exec client"
./topology/set_rtt.sh $RTT

run() { $C python3 client/client.py --mode persistent --proxy $PX --runs 1 --rtt $RTT --label $1 --csv $OUT | grep "^run"; }

$C curl -s http://$PX/__clear
echo "== Visit 1: empty cache (expect 21 MISS)"
run revisit1_empty
echo "== Visit 2: straight away (expect 21 HIT, very fast)"
run revisit2_fresh
echo "== Waiting 6 s so every entry becomes stale (TTL is 5 s)"; sleep 6
echo "== Visit 3: nothing changed (expect 21 REVALIDATE_304)"
run revisit3_stale_unchanged
echo "== Changing 5 objects (obj01..obj05), then waiting 6 s"
for i in 01 02 03 04 05; do touch server/www/obj$i.dat; done
sleep 6
echo "== Visit 4: (expect 5 REVALIDATE_200 and 16 REVALIDATE_304)"
run revisit4_stale_5changed

cp proxy/proxy.log experiments/results/revisit_proxy.log
echo
for v in 1 2 3 4; do
  echo "Visit $v results:"
  sed -n "$(( (v-1)*21+1 )),$(( v*21 ))p" proxy/proxy.log | cut -f4 | sort | uniq -c
done
echo
python3 proxy/analyze_log.py

echo
echo "== Bytes saved by one 304 (obj06.dat, fetched directly from the origin)"
URL=http://10.0.3.10:8080/obj06.dat
read H200 B200 < <($C curl -s -o /dev/null -w "%{size_header} %{size_download}\n" $URL)
ETAG=$($C curl -sI $URL | grep -i '^etag:' | cut -d' ' -f2 | tr -d '\r')
if [ -z "$ETAG" ]; then echo "Could not read the ETag. Is the origin running?"; exit 1; fi
read H304 B304 < <($C curl -s -o /dev/null -w "%{size_header} %{size_download}\n" -H "If-None-Match: $ETAG" $URL)
echo "Full 200: headers=$H200 body=$B200 total=$((H200+B200)) bytes"
echo "304:      headers=$H304 body=$B304 total=$((H304+B304)) bytes"
SAVED=$((H200+B200-H304-B304))
N304=$(grep -c REVALIDATE_304 proxy/proxy.log)
echo "Saved per 304 = $SAVED bytes"
echo "304 responses in this experiment's log = $N304  ->  total saved = $((SAVED*N304)) bytes"
./topology/set_rtt.sh 0
