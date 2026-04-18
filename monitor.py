#!/usr/bin/env python3
"""Dashgrid Linux monitor: reads /proc + statfs, POSTs CPU/mem/disk/net to Dashgrid."""

import json
import logging
import math
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

log = logging.getLogger("dashgrid-monitor")
HTTP_TIMEOUT = 10


def load_config() -> dict:
    """Load config.yaml from $DASHGRID_CONFIG or next to this script."""
    path = os.environ.get("DASHGRID_CONFIG") or str(Path(__file__).resolve().parent / "config.yaml")
    try:
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}
    except OSError as e:
        sys.exit(f"config: {e}")
    if not cfg.get("api_host"):
        sys.exit(f"config: api_host is required in {path}")
    if not cfg.get("api_key"):
        sys.exit(f"config: api_key is required in {path}")
    if not cfg.get("interval") or cfg["interval"] <= 0:
        cfg["interval"] = 10
    cfg.setdefault("buckets", {})
    return cfg


def fmt3(v: float):
    """Format float as 3-decimal number; emit None (-> JSON null) for NaN/Inf."""
    if v is None or math.isnan(v) or math.isinf(v):
        return None
    return round(float(v), 3)


def series(sk: int, v: float) -> dict:
    """Build a Dashgrid data point {"sk": <key>, "v": <value>}."""
    return {"sk": sk, "v": fmt3(v)}


def post(cfg: dict, bucket: str, records: list):
    """POST records to the Dashgrid bucket. Logs errors but never raises."""
    if not bucket:
        return
    body = json.dumps(records).encode()
    req = urllib.request.Request(
        f"{cfg['api_host']}/api/buckets/{bucket}",
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": cfg["api_key"]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            if resp.status >= 400:
                log.error("  ERROR %s: HTTP %d - %s", bucket, resp.status, resp.read(512).decode(errors="replace"))
    except urllib.error.HTTPError as e:
        log.error("  ERROR %s: HTTP %d - %s", bucket, e.code, e.read(512).decode(errors="replace"))
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        log.error("  ERROR %s: %s", bucket, e)


def read_text(path: str) -> str:
    """Read a /proc pseudo-file; return '' on error."""
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


# --- CPU ---

def read_cpu() -> tuple:
    """Return (user, nice, sys, idle, iowait, irq, sirq) from /proc/stat."""
    line = read_text("/proc/stat").split("\n", 1)[0]
    f = line.split()
    if len(f) < 8:
        return (0,) * 7
    return tuple(int(x) for x in f[1:8])


def cpu_pct(prev: tuple, cur: tuple) -> float:
    """CPU usage %: (total_delta - idle_delta) / total_delta * 100."""
    dt = sum(cur) - sum(prev)
    if dt == 0:
        return 0.0
    return (dt - (cur[3] - prev[3])) / dt * 100


def load_avg() -> tuple:
    """Return (1m, 5m, 15m) load averages from /proc/loadavg."""
    f = read_text("/proc/loadavg").split()
    if len(f) < 3:
        return 0.0, 0.0, 0.0
    return float(f[0]), float(f[1]), float(f[2])


# --- Memory ---

def read_mem() -> tuple:
    """Return (total_MB, used_MB, available_MB) from /proc/meminfo."""
    total = avail = 0
    for line in read_text("/proc/meminfo").split("\n"):
        f = line.split()
        if len(f) < 2:
            continue
        if f[0] == "MemTotal:":
            total = int(f[1]) // 1024
        elif f[0] == "MemAvailable:":
            avail = int(f[1]) // 1024
    return total, total - avail, avail


# --- Disk ---

def read_disk() -> tuple:
    """Return (total_MB, used_MB, available_MB) for '/' via statvfs."""
    try:
        fs = os.statvfs("/")
    except OSError:
        return 0, 0, 0
    bs = fs.f_frsize
    total = fs.f_blocks * bs // 1024 // 1024
    avail = fs.f_bavail * bs // 1024 // 1024
    used = total - (fs.f_bfree * bs // 1024 // 1024)
    return total, used, avail


# --- Network ---

def default_iface() -> str:
    """Find the interface for the default route in /proc/net/route."""
    for line in read_text("/proc/net/route").split("\n")[1:]:
        f = line.split()
        if len(f) >= 2 and f[1] == "00000000":
            return f[0]
    return ""


def read_net(iface: str) -> tuple:
    """Return (rx_bytes, tx_bytes) for iface from /proc/net/dev."""
    if not iface:
        return 0, 0
    prefix = iface + ":"
    for line in read_text("/proc/net/dev").split("\n"):
        line = line.strip()
        if not line.startswith(prefix):
            continue
        fields = line.split(":", 1)[1].split()
        if len(fields) < 10:
            continue
        return int(fields[0]), int(fields[8])
    return 0, 0


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y/%m/%d %H:%M:%S")
    cfg = load_config()
    buckets = cfg["buckets"]
    iface = default_iface()
    ncpu = os.cpu_count() or 1
    prev_cpu = read_cpu()
    prev_net = read_net(iface)

    log.info("started (interval: %ds, iface: %s, cores: %d)", cfg["interval"], iface, ncpu)
    interval = cfg["interval"]
    time.sleep(interval)

    while True:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rec = lambda *d: [{"k": ts, "d": list(d)}]

        # CPU: usage%
        cur_cpu = read_cpu()
        cpu_val = cpu_pct(prev_cpu, cur_cpu)
        post(cfg, buckets.get("cpu"), rec(series(1, cpu_val)))
        prev_cpu = cur_cpu

        # Load: raw 1m/5m/15m + normalized (raw / ncpu) + core count
        l1, l5, l15 = load_avg()
        post(cfg, buckets.get("load"), rec(
            series(1, l1), series(2, l5), series(3, l15),
            series(4, l1 / ncpu), series(5, l5 / ncpu), series(6, l15 / ncpu),
            series(7, ncpu),
        ))

        # Memory (MB): total, used, available
        mt, mu, ma = read_mem()
        post(cfg, buckets.get("memory"), rec(series(1, mt), series(2, mu), series(3, ma)))

        # Disk (MB): total, used, available
        dt, du, da = read_disk()
        post(cfg, buckets.get("disk"), rec(series(1, dt), series(2, du), series(3, da)))

        # Network (KB/s): rx, tx
        cur_net = read_net(iface)
        rx_kb = (cur_net[0] - prev_net[0]) / interval / 1024
        tx_kb = (cur_net[1] - prev_net[1]) / interval / 1024
        prev_net = cur_net
        post(cfg, buckets.get("network"), rec(series(1, rx_kb), series(2, tx_kb)))

        log.info("[%s] cpu=%.1f%% load=%.2f/%.2f/%.2f mem=%d/%dMB disk=%d/%dMB net=%.2f/%.2f KB/s",
                 ts, cpu_val, l1, l5, l15, mu, mt, du, dt, rx_kb, tx_kb)
        time.sleep(interval)


if __name__ == "__main__":
    main()
