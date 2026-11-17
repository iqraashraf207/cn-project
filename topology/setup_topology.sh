#!/bin/bash
# Builds: client + proxy -- br0 (in r1) -- R1 == R2 -- origin
set -e
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi

NAMESPACES="client proxy r1 r2 origin"

# 1. Clean up any old topology
for ns in $NAMESPACES; do ip netns del $ns 2>/dev/null || true; done

# 2. Create namespaces, bring up loopback
for ns in $NAMESPACES; do
  ip netns add $ns
  ip netns exec $ns ip link set lo up
done

# 3. LAN-A bridge inside R1
ip netns exec r1 ip link add br0 type bridge
ip netns exec r1 ip addr add 10.0.1.1/24 dev br0
ip netns exec r1 ip link set br0 up

# 4. Client <-> bridge
ip link add veth-c type veth peer name veth-c-br
ip link set veth-c netns client
ip link set veth-c-br netns r1
ip netns exec r1 ip link set veth-c-br master br0
ip netns exec r1 ip link set veth-c-br up
ip netns exec client ip addr add 10.0.1.10/24 dev veth-c
ip netns exec client ip link set veth-c up

# 5. Proxy <-> bridge
ip link add veth-p type veth peer name veth-p-br
ip link set veth-p netns proxy
ip link set veth-p-br netns r1
ip netns exec r1 ip link set veth-p-br master br0
ip netns exec r1 ip link set veth-p-br up
ip netns exec proxy ip addr add 10.0.1.20/24 dev veth-p
ip netns exec proxy ip link set veth-p up

# 6. Transit link R1 <-> R2 (10.0.12.0/30)
ip link add veth-r1 type veth peer name veth-r2
ip link set veth-r1 netns r1
ip link set veth-r2 netns r2
ip netns exec r1 ip addr add 10.0.12.1/30 dev veth-r1
ip netns exec r2 ip addr add 10.0.12.2/30 dev veth-r2
ip netns exec r1 ip link set veth-r1 up
ip netns exec r2 ip link set veth-r2 up

# 7. LAN-C: R2 <-> origin (10.0.3.0/24)
ip link add veth-r2o type veth peer name veth-o
ip link set veth-r2o netns r2
ip link set veth-o netns origin
ip netns exec r2 ip addr add 10.0.3.1/24 dev veth-r2o
ip netns exec origin ip addr add 10.0.3.10/24 dev veth-o
ip netns exec r2 ip link set veth-r2o up
ip netns exec origin ip link set veth-o up

# 8. Routing
ip netns exec r1 sysctl -qw net.ipv4.ip_forward=1
ip netns exec r2 sysctl -qw net.ipv4.ip_forward=1
ip netns exec client ip route add default via 10.0.1.1
ip netns exec proxy  ip route add default via 10.0.1.1
ip netns exec origin ip route add default via 10.0.3.1
ip netns exec r1 ip route add 10.0.3.0/24 via 10.0.12.2
ip netns exec r2 ip route add 10.0.1.0/24 via 10.0.12.1

echo "Topology is up."
