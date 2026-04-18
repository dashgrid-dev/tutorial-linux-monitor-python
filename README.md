# Dashgrid Linux Monitor (Python Version)

A single Python script that pushes system metrics to [Dashgrid](https://dashgrid.com) via REST API. Only runtime dependency is `PyYAML`.

## Prerequisites

1. Create a Dashgrid account and get an API key
2. Create 5 TSV data buckets per host (CPU, Load, Memory, Disk, Network)
3. Python 3.11+ on the target Linux host (`python3` and `python3-venv`)

## Metrics

| Bucket | Series 1 | Series 2 | Series 3 |
|--------|----------|----------|----------|
| CPU | usage % | — | — |
| Load | load 1m | load 5m | load 15m |
| Memory | total MB | used MB | available MB |
| Disk | total MB | used MB | available MB |
| Network | rx KB/s | tx KB/s | — |

CPU usage and load are separate buckets because they're different quantities: usage is a bounded percentage, load is an unbounded process-count. Put them on separate charts with independent axes.

### CPU
- **usage %** — percentage of CPU time spent working (not idle) since last sample. Computed as delta from `/proc/stat`.

### Load
- **load 1m / 5m / 15m** — average number of processes waiting to run over the last 1, 5, and 15 minutes. A load of 1.0 on a single-core machine means it's fully busy. Scale by number of cores.

### Memory
- **total MB** — total physical RAM installed.
- **used MB** — RAM actively in use (total minus available).
- **available MB** — RAM that can be allocated to processes without swapping. Includes free memory and reclaimable caches.

### Disk
- **total / used / available MB** — root filesystem (`/`) capacity. Uses `os.statvfs`, so values reflect the actual usable space (accounting for reserved blocks).

### Network
- **rx KB/s** — kilobytes per second received (download) on the default network interface.
- **tx KB/s** — kilobytes per second transmitted (upload). Both are computed as deltas between samples.

## Configure

Copy `config.yaml.example` to `deploy/config.yaml` and fill in your API URL, API key, and bucket IDs:

```bash
cp config.yaml.example deploy/config.yaml
```

```yaml
api_host: "your-api-host-here"
api_key: "your-api-key-here"
interval: 10

buckets:
  cpu: "bucket-id-cpu"
  load: "bucket-id-load"
  memory: "bucket-id-memory"
  disk: "bucket-id-disk"
  network: "bucket-id-network"
```

## Deploy

Copy `monitor.py`, `requirements.txt`, `deploy/setup.sh`, and `deploy/config.yaml` to the host, then run the installer:

```bash
scp monitor.py requirements.txt deploy/setup.sh deploy/config.yaml user@vm:~/monitor/
ssh user@vm 'sudo bash ~/monitor/setup.sh'
```

`setup.sh` creates a virtualenv at `~/monitor/.venv`, installs `PyYAML` into it, and registers a `systemd` service that runs `python monitor.py`.

## Verify

```bash
sudo journalctl -u dashgrid-monitor -f
```

## Update script

```bash
scp monitor.py user@vm:~/monitor/
ssh user@vm 'sudo systemctl restart dashgrid-monitor'
```

## Restart

After editing `~/monitor/config.yaml` on the host:

```bash
sudo systemctl restart dashgrid-monitor
```

## Uninstall

```bash
sudo systemctl disable --now dashgrid-monitor
sudo rm /etc/systemd/system/dashgrid-monitor.service
sudo systemctl daemon-reload
rm -rf ~/monitor/.venv
```
