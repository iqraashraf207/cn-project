#!/bin/bash
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
for ns in client proxy r1 r2 origin; do ip netns del $ns 2>/dev/null || true; done
echo "Topology removed."
