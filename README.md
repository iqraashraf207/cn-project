# HTTP/1.1 Web Server and Caching Proxy from Sockets

Course: Computer Networks
Members: Samiya Khan (24K-0768), Iqra Ashraf (24K-0952), Aseelah Masood Khan (24K-0881).

## What this project does
We built an HTTP/1.1 web server and a caching proxy using only plain TCP sockets in Python. We run them on a small
routed network (2 routers, 3 subnets) with added delay, and we measure how much **persistent connections** and
**caching** speed up loading a web page. The results are compared with the textbook model (Kurose and Ross, Chapter 2).

## What we built
| Part | File | What it does |
|---|---|---|
| Web server | `server/server.py` | GET, HEAD, POST; answers 200, 301, 304, 404; keep-alive; thread pool |
| Caching proxy | `proxy/proxy.py` | Stores responses, revalidates old ones with conditional GET (ETag, If-Modified-Since) |
| Client | `client/client.py` | Loads the test page (1 page + 20 objects) and measures load time and TCP connections |
| Network | `topology/*.sh` | Builds the network with Linux namespaces; `tc netem` adds the delay |
| Experiments | `experiments/*.sh` | Scripts for every measurement |
| Test page | `server/www/` | `index.html` and 20 objects of 10 KB each |

Network layout (IP addresses and ports): the client (10.0.1.10) and the proxy (10.0.1.20, port 8888) are in LAN-A,
router R1 connects LAN-A to R2 over a delayed link, and the web server (10.0.3.10, port 8080) is in LAN-C behind R2.
The picture is in `docs/architecture.png`.

## Requirements
Ubuntu Linux (a normal install or a VirtualBox VM) and sudo rights.
```bash
sudo apt update
sudo apt install -y python3 python3-matplotlib git curl apache2-utils tcpdump wireshark traceroute iproute2 iputils-ping
sudo modprobe sch_netem && echo "netem OK"
git clone https://github.com/iqraashraf207/cn-project.git
cd cn-project
```

## Quick check (about 20 seconds)
```bash
sudo ./experiments/smoke_test.sh
```
It builds the network, starts the server and the proxy, runs about 20 checks and cleans up. It must end with `0 failed`.

## Quick demo (3 terminals, all in the project folder)
**Terminal 3 (build the network with a 100 ms round trip):**
```bash
sudo ./topology/setup_topology.sh
sudo ./topology/verify_topology.sh        # 11 lines, all PASS
sudo ./topology/set_rtt.sh 100
```
**Terminal 1 (web server):** `sudo ip netns exec origin python3 server/server.py --port 8080 --quiet`
**Terminal 2 (proxy):** `sudo ip netns exec proxy python3 proxy/proxy.py --port 8888 --ttl 3600 --quiet`

**Terminal 3 (load the page four ways):**
```bash
sudo ip netns exec client python3 client/client.py --mode nonpersistent
sudo ip netns exec client python3 client/client.py --mode persistent
sudo ip netns exec client python3 client/client.py --mode persistent --proxy 10.0.1.20:8888 --clear-proxy
sudo ip netns exec client python3 client/client.py --mode persistent --proxy 10.0.1.20:8888
```
| Run | TCP connections | Load time at 100 ms (our results) |
|---|---|---|
| New connection for every object | 21 | about 5.5 s |
| One persistent connection | 1 | about 2.7 s |
| Through the proxy, empty cache | 1 | about 2.9 s |
| Through the proxy, warm cache | 1 | about 0.03 s |

Stop the servers with Ctrl+C and run `sudo ./topology/teardown_topology.sh` when you are done.

## Repeating the full experiments
Each script needs the network built (`setup_topology.sh`) and the web server running. The proxy scripts also need the
proxy running. Delete an old result file before rerunning (the scripts refuse to overwrite it).

| Experiment | Command | Needs | Result file |
|---|---|---|---|
| Page load time, 3 delays, 5 runs | `sudo ./experiments/run_direct.sh 5` | server | `experiments/results/direct_full.csv` |
| TCP connections per page | `sudo ./experiments/count_connections.sh persistent 100` (and `nonpersistent`) | server | SYN count printed, capture in `captures/` |
| Proxy: empty and warm cache | `sudo ./experiments/run_proxy.sh 5` | server + proxy (`--ttl 3600`) | `proxy_full.csv` |
| Requests per second | `sudo ./experiments/run_ab.sh server` or `proxy` | server (+ proxy) | `ab_server.csv`, `ab_proxy.csv` |
| Repeat visits, 304, bytes saved | `sudo ./experiments/run_revisit.sh` | server + proxy (`--ttl 5`) | `revisit.csv` |
| Figures and tables | `python3 experiments/make_plots.py` | nothing | `docs/figures/`, `docs/results_tables.md` |

## Main results (details in `docs/analysis.md`)
- A new connection per object needs **21** TCP connections; persistent HTTP needs **1**. Persistent HTTP was about 2 times faster.
- A warm proxy cache loads the page in about 0.03 s at every delay, because no packet crosses the delayed link.
- Cache hit ratio: 0.800 for five page loads. A 304 response saves about 10,300 bytes compared with a full 200.
- The measured times are above the textbook model (about 15% to 30% at 100 and 200 ms) because of timing noise in the
  virtual machine. We explain this in `docs/analysis.md`.

## Evidence
Packet captures (`captures/`), annotated screenshots (`docs/evidence/screenshots/`), routing tables, traceroute and
ping results (`docs/evidence/`). `docs/evidence/INDEX.md` lists every file.

## Common problems
- `Address already in use`: an old server is still running. Run `pkill -f server/server.py; pkill -f proxy/proxy.py`.
- `netem` not found: run `sudo modprobe sch_netem` or `sudo apt install linux-modules-extra-$(uname -r)`.
- Packet capture with `dumpcap` fails with "Permission denied": write the file to `/tmp` first, then move it to `captures/`.

