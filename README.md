# ptp-experiments

Ansible for a home-lab GNSS-disciplined PTP grandmaster and its clients,
plus the monitoring that watches the whole chain.

## Fleet

| Host | Role | Hardware |
|---|---|---|
| 10.3.30.64 (`mu`) | grandmaster, stratum-1 NTP for 10.3.0.0/16 | x86, OCP Time Card (`ptp_ocp`), TimeNIC Intel i226 (`enp1s0`, `igc`) |
| 10.3.30.11 | PTP client | Pi 5, onboard NIC (PHC on the Broadcom PHY) |
| 10.3.30.12 | PTP client | Pi, PCIe Intel i226 (`enP1p1s0`) |

## Grandmaster pipeline profiles

The GM's NIC-PHC discipline leg is switchable. `gm_pipeline` in
`group_vars/ptp_server.yml` names a profile file in `vars/gm_pipelines/`:

- **`timecard-ts2phc`** (default, hardware):
  GNSS → Timecard FPGA PHC → chrony (NTP) and SMA "OUT: PHC" PPS →
  SMA cable → i226 SDP1 → `ts2phc` → NIC PHC (`/dev/ptp-nic`) → `ptp4l`.
  Needs the igc-ppsfix driver loaded and `timecard_sma` routing "OUT: PHC"
  on the cabled connector. ~6 ns rms on the TICC.
- **`timecard-phc2sys`** (software comparison):
  chrony disciplines `CLOCK_REALTIME` from the Timecard PHC; `phc2sys`
  steers the NIC PHC from `CLOCK_REALTIME`; `ptp4l` serves it. No SMA/EXTTS
  involvement.

Switch with one variable and a scoped deploy:

```
ansible-playbook deploy.yml -e gm_pipeline=timecard-phc2sys --tags ptp,monitoring
```

(or edit `group_vars/ptp_server.yml` to make it stick). `roles/gm_pipeline`
stops, disables, and removes the inactive leg's unit, so switching
converges. The metrics script and Prometheus alerts follow the profile;
`gm:nic_phc_offset_ns` / `gm:nic_phc_freq_ppb` recording rules feed the PTP
dashboard from whichever leg is active. Adding a profile = one new vars
file (plus a converge block in `roles/gm_pipeline` if it introduces a new
service).

Note: `phc2sys.service` was also the name of a long-removed legacy unit
that once steered client system clocks; the fleet was purged before the
profile reused the name.

## Layout

- `deploy.yml` — the main playbook; a grandmaster play and a clients play.
  Tags: `timecard`, `tgpio`, `igc`, `reboot`, `ptp`, `chrony`,
  `monitoring`, `ticc`. (Node IPs are provisioned by netboot; nothing here
  manages addressing.)
- `reset.yml` — hard-reset CM5 nodes (VC reboot flags + reboot); requires
  `-e reset_hosts=...`.
- `tasks/`, `handlers/` — flattened single-play pieces too small for a role
  (currently gpsd, grandmaster only).
- `roles/` — `timecard` (udev rules + SMA routing),
  `chrony` (GM and clients, fragments converge on their vars),
  `igc_ppsfix` (host source build of the PPS-fixed igc, like `timecard`'s
  ptp_ocp build), `linuxptp` (source build,
  pinned commit in `group_vars/all.yml`), `ptp4l`, `gm_pipeline`,
  `ptp_metrics` (textfile collector), `monitoring_server` (GM), and
  `monitoring_agent` (clients).
- `vars/gm_pipelines/` — one file per GM pipeline profile.
- `files/dashboards/` — Grafana dashboard JSON, source of record.
- `analysis/` — marimo notebook for TICC ADEV analysis (not deployed).

## Install paths

Hardcoded in the roles, not variables — there is one correct answer per
class (FHS 3.0):

- `/usr/local/sbin/` — everything installed: the linuxptp binaries (`make
  install`, default prefix), `testptp`, the exporters, and the local
  systemd-invoked scripts. All root-only, hence `sbin` not `bin` (3.16.1).
- `/usr/local/src/<name>/` — local source and build trees: `linuxptp`,
  `testptp`, `ptp_ocp`, `igc-ppsfix`, `gpsd-prometheus-exporter`,
  `tgpio` (the SSDT `.asl`/`.aml`). Built in place; only the artifact is
  installed.
- `/var/cache/chrony_exporter/` — the downloaded release tarball; a
  regenerable cache, safe to delete.
- `/etc/` — all config (`linuxptp/`, `chrony/conf.d/`, `modprobe.d/`,
  `udev/rules.d/`, `systemd/system/`, `default/grub.d/`).
- Kernel modules go where the kernel expects them:
  `/lib/modules/<kver>/updates/`.

## Stable device names

`/dev/ptpN` numbering depends on probe order, so nothing references it:

- `/dev/ptp-timecard` — Timecard PHC
  (`roles/timecard/files/99-ptp-timecard.rules`).
- `/dev/ptp-nic` — the PHC `ptp4l` uses, matched by parent driver
  (`nic_phc_driver`: `igc` on i226 hosts, the Broadcom PHY driver on Pi 5
  onboard — the Pi exposes a second, wrong PHC on the MAC).

## Patched drivers

Both are built on the host from vendored source and installed to
`/lib/modules/<kver>/updates/` (no DKMS: after a kernel upgrade the stock
drivers run until the next deploy run rebuilds for the new kernel):

- **igc-ppsfix** (`roles/igc_ppsfix`, source in its `files/src/`) — i226
  EXTTS/PEROUT fixes; required for ts2phc on the TimeNIC. Installs **to
  disk only** and loads at the next reboot via deploy.yml's shared reboot
  task — never reloaded live: the igc NIC carries the SSH session.
- **ptp_ocp** (`roles/timecard`, source in its `files/src/`) — out-of-tree
  PTM-capable build. **Required**: the Time Card runs a PTM FPGA image the
  stock in-tree driver cannot drive (all-ones registers, wedged udev —
  looks exactly like dead hardware). Loaded live by the role.

After a kernel upgrade, re-run the deploy: the igc role keeps flagging the
reboot on every run until the *running* module matches the on-disk build.

## Monitoring

Prometheus (`:9090`, exposed) plus chrony/gpsd/node exporters run on the GM
via docker compose; clients run `prometheus-node-exporter` and the shared
`ptp-metrics.sh` textfile collector. **Grafana lives on the homelab Grafana
server**, not here:

- Add a datasource with **uid `prometheus`** pointing at
  `http://10.3.30.64:9090` — every dashboard JSON hardcodes that uid.
- Import `files/dashboards/*.json` by hand (a named folder, e.g. "PTP", is
  recommended). Re-import after editing the JSONs here.
- Alert rules evaluate in Prometheus (`/alerts`); no Alertmanager yet.
- `/opt/monitoring/grafana` on the GM is the old local Grafana's data dir —
  delete it once the homelab Grafana is confirmed good.

## Deploying

```
ansible-galaxy collection install -r requirements.yml   # once
ansible-playbook deploy.yml                             # whole fleet
ansible-playbook deploy.yml --limit ptp_clients         # clients only
ansible-playbook deploy.yml --tags monitoring           # monitoring only
```

Deploys restart time services when their configs change — avoid mid-measurement.

## Verifying

GM: `chronyc sources -v` (AC selected, stratum 1), `journalctl -u ts2phc`
(or `-u phc2sys`) for ns-class offsets in `s2`, Prometheus `/targets` and
`/rules`. Clients: `/usr/local/sbin/pmc -u -b 0 'GET CURRENT_DATA_SET'`
(ns-class offset, stepsRemoved 1), `chronyc tracking` (ref `PHC`, leap
Normal), `ls -l /dev/ptp-nic`.
