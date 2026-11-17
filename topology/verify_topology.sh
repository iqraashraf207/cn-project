#!/bin/bash
if [ "$EUID" -ne 0 ]; then echo "Run with sudo"; exit 1; fi
t() {  # t <from-ns> <target-ip>
  if ip netns exec "$1" ping -c 2 -W 2 "$2" >/dev/null 2>&1; then
    echo "PASS  $1 -> $2"
  else
    echo "FAIL  $1 -> $2"
  fi
}
t client 10.0.1.1
t client 10.0.1.20
t proxy  10.0.1.1
t client 10.0.12.2
t client 10.0.3.1
t client 10.0.3.10
t proxy  10.0.3.10
t origin 10.0.1.10
t origin 10.0.1.20
t r1 10.0.3.10
t r2 10.0.1.10
