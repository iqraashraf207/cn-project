#!/bin/bash
# needs topology up, origin server running. 
# counts the TCP connections of ONE page load two ways: (1)distinct client ports seen by sampling 'ss', (2)SYN packets in a tcpdump capture
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
cd "$(dirname "$0")/.."
MODE=$1
RTT=${2:-100}
if [ "$MODE" != persistent ] && [ "$MODE" != nonpersistent ]; then
  echo "Usage: sudo $0 persistent|nonpersistent [rtt_ms]"; exit 1
fi
./topology/set_rtt.sh $RTT
PCAP=captures/connections_${MODE}_rtt${RTT}.pcap
SS=docs/evidence/ss_samples_${MODE}_rtt${RTT}.txt

ip netns exec client tcpdump -i veth-c -n -Z root -w $PCAP 'tcp port 8080' 2> /dev/null &
sleep 1
( for i in $(seq 1 200); do
    ip netns exec client ss -Htn state established '( dport = :8080 )'
    sleep 0.05
  done ) > $SS &
SS_PID=$!

ip netns exec client python3 client/client.py --mode $MODE --runs 1 --rtt $RTT --label conncheck

sleep 1
kill $SS_PID 2> /dev/null
pkill -INT -f "tcpdump -i veth-c"
sleep 1
SYNS=$(tcpdump -nn -r $PCAP 'tcp[tcpflags] & (tcp-syn|tcp-ack) == tcp-syn' 2> /dev/null | wc -l)
PORTS=$(awk '{print $3}' $SS | sort -u | wc -l)
echo "SYN packets (client -> origin) in $PCAP : $SYNS"
echo "Distinct client ports seen by ss ($SS) : $PORTS"
./topology/set_rtt.sh 0
