#!/bin/bash
# Usage: sudo ./experiments/smoke_test.sh
# Builds the topology, starts origin + proxy, runs end-to-end checks, tears everything down.
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
cd "$(dirname "$0")/.."
PASS=0; FAIL=0
C="ip netns exec client"
PXLOG=/tmp/smoke_proxy.log

check() {   # check "description" expected actual
  if [ "$2" = "$3" ]; then echo "PASS  $1"; PASS=$((PASS+1))
  else echo "FAIL  $1 (expected '$2', got '$3')"; FAIL=$((FAIL+1)); fi
}
field() { echo "$1" | sed -E "s/.* $2=([^ ]+).*/\1/"; }   # field "<run line>" connections
cleanup() {
  pkill -f "server/server.py" 2> /dev/null
  pkill -f "proxy/proxy.py" 2> /dev/null
  ./topology/set_rtt.sh 0 > /dev/null 2>&1
  ./topology/teardown_topology.sh > /dev/null 2>&1
}
trap cleanup EXIT
cleanup

./topology/setup_topology.sh > /dev/null
ip netns exec origin python3 server/server.py --port 8080 --quiet &
ip netns exec proxy python3 proxy/proxy.py --port 8888 --ttl 3600 --quiet --log $PXLOG &
sleep 1.5

echo "== Topology"
for t in "client 10.0.1.1" "client 10.0.1.20" "client 10.0.3.10" "origin 10.0.1.10"; do
  set -- $t
  if ip netns exec $1 ping -c 1 -W 2 $2 > /dev/null 2>&1; then check "ping $1 -> $2" ok ok
  else check "ping $1 -> $2" ok unreachable; fi
done
./topology/set_rtt.sh 20 > /dev/null
AVG=$($C ping -c 5 -q 10.0.3.10 | awk -F/ '/^rtt/ {print $5}')
if awk -v a="${AVG:-0}" 'BEGIN{exit !(a>=19 && a<=26)}'; then check "RTT with netem 20 ms (measured ${AVG} ms)" ok ok
else check "RTT with netem 20 ms" "19-26 ms" "${AVG:-none} ms"; fi

echo "== Origin server (direct)"
R=$($C python3 client/client.py --mode persistent | grep '^run')
check "persistent: 1 TCP connection" 1 "$(field "$R" connections)"
check "persistent: 21 requests, all 200" "21 True" "$(field "$R" requests) $(field "$R" all_ok)"
R=$($C python3 client/client.py --mode nonpersistent | grep '^run')
check "non-persistent: 21 TCP connections" 21 "$(field "$R" connections)"
U=http://10.0.3.10:8080
check "404 for a missing file" 404 "$($C curl -s -o /dev/null -w '%{http_code}' $U/nothing.html)"
check "301 for /old.html" 301 "$($C curl -s -o /dev/null -w '%{http_code}' $U/old.html)"
ETAG=$($C curl -sI $U/obj01.dat | grep -i '^etag:' | cut -d' ' -f2 | tr -d '\r')
check "304 with If-None-Match" 304 "$($C curl -s -o /dev/null -w '%{http_code}' -H "If-None-Match: $ETAG" $U/obj01.dat)"
check "HEAD returns 200" 200 "$($C curl -sI -o /dev/null -w '%{http_code}' $U/obj01.dat)"
check "POST returns body" "Received 11 bytes" "$($C curl -s -d 'hello=world' $U/submit)"

echo "== Caching proxy"
PX=10.0.1.20:8888
R=$($C python3 client/client.py --mode persistent --proxy $PX --clear-proxy | grep '^run')
check "proxy, empty cache: 1 client connection, all 200" "1 True" "$(field "$R" connections) $(field "$R" all_ok)"
check "proxy, empty cache: 21 MISS in log" 21 "$(cut -f4 $PXLOG | grep -c '^MISS$')"
R=$($C python3 client/client.py --mode persistent --proxy $PX | grep '^run')
check "proxy, warm cache: 21 HIT in log" 21 "$(cut -f4 $PXLOG | grep -c '^HIT$')"
T=$(field "$R" load_time | tr -d s)
if awk -v t="${T:-9}" 'BEGIN{exit !(t<0.15)}'; then check "warm load time under 0.15 s (${T} s)" ok ok
else check "warm load time under 0.15 s" "<0.15" "$T"; fi
check "POST through proxy" "Received 11 bytes" "$($C curl -s -x http://$PX -d 'hello=world' $U/submit)"
check "POST logged as BYPASS" BYPASS "$(tail -1 $PXLOG | cut -f4)"
check "404 through proxy" 404 "$($C curl -s -o /dev/null -w '%{http_code}' -x http://$PX $U/nothing.html)"

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
