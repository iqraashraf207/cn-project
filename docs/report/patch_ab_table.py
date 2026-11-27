"""run once from the project root after build_report.py exists"""
import os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_report.py")
if not os.path.exists(p):
    raise SystemExit("build_report.py not found: create it first")
s = open(p).read()
if "Median req/s" in s:
    raise SystemExit("already patched")
a, b = s.index("def t_ab():"), s.index("TABLES = {")
new = '''def t_ab():
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
                    "Server and proxy were measured on different machines.")


'''
open(p, "w").write(s[:a] + new + s[b:])
print("patched", p)
