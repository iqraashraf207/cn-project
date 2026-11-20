#!/usr/bin/env python3
"""Draws docs/architecture.png (topology, addresses, ports, interfaces, protocol flows)."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

fig, ax = plt.subplots(figsize=(17, 9))
ax.set_xlim(0, 17.5)
ax.set_ylim(0, 9.4)
ax.axis("off")


def box(x, y, w, h, text, fc="#eef3fb", ec="#2b4a7a", fs=10, bold_first=True):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05", fc=fc, ec=ec, lw=1.6))
    lines = text.split("\n")
    ax.text(x + w / 2, y + h - 0.28, lines[0], ha="center", va="top", fontsize=fs + 1,
            fontweight="bold" if bold_first else "normal")
    ax.text(x + w / 2, y + h - 0.7, "\n".join(lines[1:]), ha="center", va="top", fontsize=fs,
            linespacing=1.5)


# LAN-A background
ax.add_patch(Rectangle((0.2, 1.9), 7.2, 5.4, fc="#f7fbf2", ec="#5b8a3c", lw=1.4, ls="--"))
ax.text(0.4, 7.15, "LAN-A  10.0.1.0/24  (no added delay)", fontsize=11, color="#3d6b25", va="top",
        fontweight="bold")
ax.add_patch(Rectangle((11.4, 1.9), 5.8, 5.4, fc="#fdf6ee", ec="#b5742a", lw=1.4, ls="--"))
ax.text(11.6, 7.15, "LAN-C  10.0.3.0/24", fontsize=11, color="#8a5518", va="top", fontweight="bold")

box(0.5, 4.9, 2.8, 1.7, "Client (ns: client)\nveth-c  10.0.1.10/24\ngw 10.0.1.1")
box(0.5, 2.3, 2.8, 1.9, "Caching proxy (ns: proxy)\nveth-p  10.0.1.20/24\nTCP 8888 (configurable)\ngw 10.0.1.1")
box(4.3, 2.3, 3.0, 4.3, "R1 (ns: r1)\nip_forward = 1\nbridge br0  10.0.1.1/24\n(LAN-A side)\n\nveth-r1  10.0.12.1/30\n(transit side)\nroute 10.0.3.0/24\nvia 10.0.12.2")
box(9.3, 2.3, 3.0, 4.3, "R2 (ns: r2)\nip_forward = 1\nveth-r2  10.0.12.2/30\n(transit side)\n\nveth-r2o  10.0.3.1/24\n(LAN-C side)\nroute 10.0.1.0/24\nvia 10.0.12.1")
box(13.8, 3.0, 3.1, 2.6, "Origin server (ns: origin)\nveth-o  10.0.3.10/24\nTCP 8080 (configurable)\ngw 10.0.3.1")

# links
for (x1, y1, x2, y2) in [(3.3, 5.75, 4.3, 5.75), (3.3, 3.25, 4.3, 3.25)]:
    ax.plot([x1, x2], [y1, y2], color="#444", lw=2)
ax.text(3.8, 5.95, "veth", fontsize=8, ha="center")
ax.text(3.8, 3.45, "veth", fontsize=8, ha="center")
ax.plot([7.3, 9.3], [4.45, 4.45], color="#c0392b", lw=4)
ax.text(8.3, 5.0, "LAN-B 10.0.12.0/30\ntc netem delay\n(RTT/2 on each side)", ha="center", fontsize=9,
        color="#c0392b", fontweight="bold", linespacing=1.4)
ax.text(8.3, 3.85, "20 / 100 / 200 ms RTT", ha="center", fontsize=9, color="#c0392b")
ax.plot([12.3, 13.8], [4.3, 4.3], color="#444", lw=2)
ax.text(13.05, 4.5, "veth", fontsize=8, ha="center")

# proxy-mode flows
ax.annotate("", xy=(1.9, 4.2), xytext=(1.9, 4.9),
            arrowprops=dict(arrowstyle="<->", color="#1f6fb2", lw=2.2))
ax.text(2.05, 4.55, "HTTP/1.1 :8888", fontsize=9, color="#1f6fb2", va="center")
ax.plot([1.9, 1.9, 16.0], [2.3, 1.1, 1.1], color="#1f6fb2", lw=2.2)
ax.annotate("", xy=(16.0, 3.0), xytext=(16.0, 1.1),
            arrowprops=dict(arrowstyle="->", color="#1f6fb2", lw=2.2))
ax.text(8.9, 0.8, "Proxy mode, leg 2: proxy -> origin, HTTP/1.1 to TCP 8080 (conditional GET with "
        "If-None-Match / If-Modified-Since), crosses the delayed link", ha="center", fontsize=9,
        color="#1f6fb2")
# direct-mode flow
ax.plot([1.2, 1.2, 15.3], [6.6, 8.3, 8.3], color="#7d3c98", lw=2.2, ls="--")
ax.annotate("", xy=(15.3, 5.6), xytext=(15.3, 8.3),
            arrowprops=dict(arrowstyle="->", color="#7d3c98", lw=2.2, ls="--"))
ax.text(8.3, 8.5, "Direct mode: client -> origin, HTTP/1.1 to TCP 8080 (keep-alive or Connection: close), "
        "crosses the delayed link", ha="center", fontsize=9, color="#7d3c98")

ax.text(8.75, 9.1, "Topology: one laptop, Linux network namespaces (3 subnets, 2 routers, static routes)",
        ha="center", fontsize=13, fontweight="bold")
ax.text(8.75, 0.25, "Protocols: HTTP/1.0 and 1.1 over TCP/IPv4; ICMP for ping and traceroute. "
        "Blue = proxy mode, purple dashed = direct mode.", ha="center", fontsize=9)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "architecture.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("Wrote", out)
