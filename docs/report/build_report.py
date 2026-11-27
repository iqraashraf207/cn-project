#!/usr/bin/env python3
"""builds docs/report/report.docx from the section files"""
import csv
import os
import re
import statistics
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RES = os.path.join(ROOT, "experiments", "results")
PARTS = ["00_front.md", "01_iqra.md", "02_samiya.md", "03_captures_iqra.md",
         "04_captures_samiya.md", "05_closing.md", "06_end.md"]
RTTS = [20, 100, 200]


def read_csv(name):
    p = os.path.join(RES, name)
    if not os.path.exists(p):
        print("MISSING:", p)
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def read_log(name):
    p = os.path.join(RES, name)
    if not os.path.exists(p):
        print("MISSING:", p)
        return []
    with open(p) as f:
        return [l.rstrip("\n").split("\t") for l in f if len(l.rstrip("\n").split("\t")) == 6]


def msd(v):
    return statistics.mean(v), (statistics.stdev(v) if len(v) > 1 else 0.0)


def md_table(headers, rows, caption):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out) + f"\n\nTable: {caption}\n"


def page_stats():
    rows = read_csv("direct_full.csv") + read_csv("proxy_full.csv")
    st = {}
    for r in rows:
        key = (r["label"], r["mode"], int(r["rtt_ms"]))
        st.setdefault(key, []).append(r)
    res = {}
    for k, rs in st.items():
        t = [float(r["load_time_s"]) for r in rs]
        m, sd = msd(t)
        res[k] = (m, sd, statistics.mean(int(r["connections"]) for r in rs), len(t))
    return res


def t_load_time():
    s = page_stats()
    cell = lambda k: f"{s[k][0]:.3f} ± {s[k][1]:.3f}" if k in s else "-"
    rows = [[rtt, cell(("direct", "nonpersistent", rtt)), f"{42 * rtt / 1000:.3f}",
             cell(("direct", "persistent", rtt)), f"{22 * rtt / 1000:.3f}",
             cell(("proxy_empty", "persistent", rtt)), cell(("proxy_warm", "persistent", rtt))]
            for rtt in RTTS]
    return md_table(["RTT (ms)", "Direct, non-persistent (s)", "Model 42 RTT (s)", "Direct, persistent (s)",
                     "Model 22 RTT (s)", "Proxy, empty cache (s)", "Proxy, warm cache (s)"], rows,
                    "Page load time, mean ± standard deviation of 5 runs (21 requests fetched one at a time).")


def t_connections():
    s = page_stats()
    names = [("direct", "nonpersistent", "Direct, non-persistent"), ("direct", "persistent", "Direct, persistent"),
             ("proxy_empty", "persistent", "Through proxy, empty cache"),
             ("proxy_warm", "persistent", "Through proxy, warm cache")]
    rows = []
    for lab, mode, name in names:
        v = [s[(lab, mode, r)][2] for r in RTTS if (lab, mode, r) in s]
        if v:
            rows.append([name, f"{statistics.mean(v):.0f}", 21])
    return md_table(["Case", "TCP connections per page (client side)", "HTTP requests"], rows,
                    "TCP connections opened by the client for one page load.")


def t_derived():
    s = page_stats()
    rows = []
    for rtt in RTTS:
        a, b = s.get(("direct", "nonpersistent", rtt)), s.get(("direct", "persistent", rtt))
        c, d = s.get(("proxy_empty", "persistent", rtt)), s.get(("proxy_warm", "persistent", rtt))
        rows.append([rtt, f"{a[0] / b[0]:.2f}" if a and b else "-", f"{a[0] - b[0]:.2f}" if a and b else "-",
                     f"{(c[0] - b[0]) / b[0] * 100:+.1f}%" if b and c else "-",
                     f"{b[0] / d[0]:.0f}x" if b and d else "-"])
    return md_table(["RTT (ms)", "Non-persistent / persistent (model 1.91)", "Seconds saved by persistence",
                     "Proxy (empty cache) vs direct persistent", "Warm proxy speed-up vs direct persistent"],
                    rows, "Derived comparisons.")


def t_revisit():
    rv, lg = read_csv("revisit.csv"), read_log("revisit_proxy.log")
    names = ["1 (empty cache)", "2 (fresh entries)", "3 (stale, nothing changed)", "4 (stale, 5 objects changed)"]
    rows = []
    for v in range(min(4, len(rv))):
        c = defaultdict(int)
        for p in lg[v * 21:(v + 1) * 21]:
            c[p[3]] += 1
        rows.append([names[v], f"{float(rv[v]['load_time_s']):.3f}",
                     ", ".join(f"{n} {k}" for k, n in sorted(c.items()))])
    return md_table(["Visit", "Load time (s), RTT 100 ms", "Proxy log outcomes"], rows,
                    "Repeat visits through the proxy (TTL 5 s, one run per visit).")


def t_hitratio():
    gets = [p for p in read_log("hitratio_proxy.log") if p[1] == "GET"]
    loads = [gets[i:i + 21] for i in range(0, len(gets) - 20, 21)]
    rows = []
    for i, L in enumerate(loads):
        h = sum(1 for p in L if p[3] in ("HIT", "REVALIDATE_304"))
        rows.append([i + 1, h, 21 - h])
    tot = sum(r[1] for r in rows) / max(1, len(gets))
    return md_table(["Page load", "Hits (HIT or REVALIDATE_304)", "Misses"], rows,
                    f"Cache outcome of 5 consecutive page loads. Overall hit ratio = {tot:.3f} over {len(gets)} GET requests.")


def t_bytes():
    p = os.path.join(ROOT, "docs", "evidence", "revisit_output.txt")
    if not os.path.exists(p):
        print("MISSING:", p)
        return ""
    t = open(p).read()
    a = re.search(r"Full 200: headers=(\d+) body=(\d+) total=(\d+)", t)
    b = re.search(r"304:\s+headers=(\d+) body=(\d+) total=(\d+)", t)
    c = re.search(r"Saved per 304 = (\d+) bytes", t)
    d = re.search(r"log = (\d+)\s+->\s+total saved = (\d+) bytes", t)
    if not (a and b and c and d):
        print("bytes-saved lines not found in revisit_output.txt")
        return ""
    rows = [["Full 200 response (headers + body)", f"{a.group(3)} B"], ["304 response (headers only)", f"{b.group(3)} B"],
            ["Saved per 304", f"{c.group(1)} B"], ["304 responses in the repeat-visit experiment", d.group(1)],
            ["Total saved", f"{d.group(2)} B"]]
    return md_table(["Item", "Value"], rows, "Bytes saved by 304 responses.")


def t_ab():
    out_rows = []
    for t in ("server", "proxy"):
        g = defaultdict(list)
        for r in read_csv(f"ab_{t}.csv"):
            if r["requests_per_sec"] != "NA":
                g[(int(r["concurrency"]), r["keepalive"])].append(float(r["requests_per_sec"]))
        for c in (1, 10, 50):
            for ka in ("no", "yes"):
                v = g.get((c, ka))
                if v:
                    out_rows.append(["Origin server" if t == "server" else "Caching proxy (hits)", c,
                                     "yes (-k)" if ka == "yes" else "no",
                                     f"{statistics.median(v):.0f}", f"{min(v):.0f}-{max(v):.0f}"])
    return md_table(["Target", "Concurrency", "Keep-alive", "Median req/s", "Min-max req/s"], out_rows,
                    "ApacheBench throughput: median and range of 3 runs of 3000 requests each. "
                    "Server and proxy were measured on the same machine.")


TABLES = {"load_time": t_load_time, "connections": t_connections, "derived": t_derived, "revisit": t_revisit,
          "hitratio": t_hitratio, "bytes": t_bytes, "ab": t_ab}


def expand(text):
    def tab(m):
        fn = TABLES.get(m.group(1))
        if not fn:
            print("UNKNOWN TABLE:", m.group(1))
            return m.group(0)
        return "\n" + fn() + "\n"

    def fil(m):
        p = os.path.join(ROOT, m.group(1))
        if not os.path.exists(p):
            print("MISSING FILE:", m.group(1))
            return m.group(0)
        return "\n```\n" + open(p).read().rstrip() + "\n```\n"
    text = re.sub(r"@@TABLE:(\w+)@@", tab, text)
    return re.sub(r"@@FILE:([^@]+)@@", fil, text)


def main():
    full, problems = [], 0
    for name in PARTS:
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            print("MISSING PART:", name)
            problems += 1
            continue
        full.append(expand(open(p).read()))
    text = "\n\n".join(full)
    for m in re.finditer(r"\[WRITE[^\]]*\]|\[\.\.\]|<[A-Z ]+>", text):
        print("UNFINISHED:", m.group(0)[:70])
        problems += 1
    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
        if not os.path.exists(os.path.join(HERE, m.group(1))):
            print("MISSING IMAGE:", m.group(1))
            problems += 1
    for m in re.finditer(r"@@[A-Z]+:[^@]*@@", text):
        print("UNRESOLVED:", m.group(0))
        problems += 1
    out_md = os.path.join(HERE, "report_full.md")
    with open(out_md, "w") as f:
        f.write(text + "\n")
    print(f"wrote {out_md} ({len(text.split())} words), problems: {problems}")
    if "--no-pandoc" in sys.argv:
        return
    cmd = ["pandoc", out_md, "-o", os.path.join(HERE, "report.docx"), "--toc", "--toc-depth=2",
           "--number-sections", "--resource-path", HERE]
    try:
        subprocess.run(cmd, check=True, cwd=HERE)
        print("wrote", os.path.join(HERE, "report.docx"))
    except (OSError, subprocess.CalledProcessError) as e:
        print("pandoc failed:", e)


if __name__ == "__main__":
    main()
