#!/usr/bin/env python3
"""Summarise proxy.log. Usage: python3 proxy/analyze_log.py [logfile]"""
import os
import sys
from collections import Counter

default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.log")
path = sys.argv[1] if len(sys.argv) > 1 else default
counts, gets, total_bytes = Counter(), 0, 0
with open(path) as f:
    for line in f:
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 6:
            continue
        _, method, _, result, _, nbytes = parts
        counts[result] += 1
        total_bytes += int(nbytes)
        if method == "GET":
            gets += 1
for r in ("HIT", "MISS", "REVALIDATE_304", "REVALIDATE_200", "BYPASS"):
    print(f"{r:15s} {counts[r]}")
print(f"{'GET requests':15s} {gets}")
print(f"{'Bytes to clients':15s} {total_bytes}")
if gets:
    ratio = (counts["HIT"] + counts["REVALIDATE_304"]) / gets
    print(f"Cache hit ratio = (HIT + REVALIDATE_304) / GETs = {ratio:.3f}")

