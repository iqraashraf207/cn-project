#!/usr/bin/env python3
"""summarise result CSVs (page-load CSVs from client.py or ab CSVs from run_ab.sh)"""
import argparse
import csv
import statistics
from collections import defaultdict


def mean_sd(v):
    return statistics.mean(v), (statistics.stdev(v) if len(v) > 1 else 0.0)


def model_rtts(label, mode):
    """textbook model:RTTs needed for 21 requests fetched one at a time"""
    if label.startswith("direct"):
        return 42 if mode == "nonpersistent" else 22
    if label == "proxy_empty":
        return 22
    return None


def pageload(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["label"], r["mode"], int(r["rtt_ms"]))].append(r)
    header = ["label", "mode", "rtt_ms", "runs", "mean_s", "stdev_s", "min_s", "max_s",
              "connections", "model_s", "diff_vs_model"]
    table = []
    for (label, mode, rtt), rs in sorted(groups.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1])):
        times = [float(r["load_time_s"]) for r in rs]
        m, sd = mean_sd(times)
        conns = statistics.mean(int(r["connections"]) for r in rs)
        k = model_rtts(label, mode)
        model = k * rtt / 1000 if k else None
        diff = f"{(m - model) / model * 100:+.1f}%" if model else "-"
        if not all(r["all_ok"] == "True" for r in rs):
            diff += " (!! some runs not all_ok)"
        table.append([label, mode, rtt, len(rs), f"{m:.4f}", f"{sd:.4f}", f"{min(times):.4f}",
                      f"{max(times):.4f}", f"{conns:.1f}", f"{model:.3f}" if model else "-", diff])
    return header, table


def ab(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["target"], r["keepalive"], int(r["concurrency"]))].append(r)
    header = ["target", "keepalive", "concurrency", "runs", "mean_req_per_s", "stdev", "failed_total"]
    table = []
    for (target, ka, c), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1])):
        rps = [float(r["requests_per_sec"]) for r in rs if r["requests_per_sec"] != "NA"]
        failed = sum(int(r["failed"]) for r in rs if r["failed"] != "NA")
        if not rps:
            continue
        m, sd = mean_sd(rps)
        table.append([target, ka, c, len(rps), f"{m:.1f}", f"{sd:.1f}", failed])
    return header, table


def show(header, table):
    widths = [max(len(str(x)) for x in col) for col in zip(header, *table)]
    for row in [header] + table:
        print("  ".join(str(x).ljust(w) for x, w in zip(row, widths)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=None, help="also write the tables to this CSV")
    args = ap.parse_args()
    page_rows, ab_rows = [], []
    for fn in args.files:
        with open(fn, newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        (ab_rows if "requests_per_sec" in rows[0] else page_rows).extend(rows)
    tables = []
    if page_rows:
        tables.append(pageload(page_rows))
    if ab_rows:
        tables.append(ab(ab_rows))
    for h, t in tables:
        if t:
            show(h, t)
            print()
    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.writer(f)
            for h, t in tables:
                w.writerow(h)
                w.writerows(t)
                w.writerow([])
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
