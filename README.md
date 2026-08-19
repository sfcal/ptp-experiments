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

- `deploy.yml` — the only playbook; a grandmaster play and a clients play.
  Tags: `network`, `gpsd`, `timecard`, `chrony`, `dkms`, `ptp`, `pipeline`,
  `monitoring`.
- `roles/` — `network`, `gpsd`, `timecard` (udev rules + SMA routing),
  `chrony` (GM and clients, fragments converge on their vars), `dkms_module`
  (parameterized, used for both patched drivers), `linuxptp` (source build,
  pinned commit in `group_vars/all.yml`), `ptp4l`, `gm_pipeline`,
  `ptp_metrics` (textfile collector), `monitoring_server` (GM), and
  `monitoring_agent` (clients).
- `vars/gm_pipelines/` — one file per GM pipeline profile.
- `igc-ppsfix/`, `ptp-ocp-gnsspps/` — patched-driver DKMS sources and docs.
- `files/dashboards/` — Grafana dashboard JSON, source of record.
- `analysis/` — marimo notebook for TICC ADEV analysis (not deployed).

## Stable device names

`/dev/ptpN` numbering depends on probe order, so nothing references it:

- `/dev/ptp-timecard`, `/dev/pps-timecard` — Timecard PHC and kernel PPS
  (`roles/timecard/files/timecard-ptp.rules`).
- `/dev/ptp-nic` — the PHC `ptp4l` uses, matched by parent driver
  (`nic_phc_driver`: `igc` on i226 hosts, the Broadcom PHY driver on Pi 5
  onboard — the Pi exposes a second, wrong PHC on the MAC).

## Patched drivers (DKMS)

Both install **to disk only** and load at the next reboot; Ansible flags
`/run/reboot-required` and never reloads live (the igc NIC carries the SSH
session; chrony/ts2phc/gpsd hold the Time Card open). Opt in to automatic
reboots per host with `igc_ppsfix_auto_reboot` / `ptp_ocp_gnsspps_auto_reboot`.

- **igc-ppsfix** — i226 EXTTS/PEROUT fixes; required for ts2phc on the
  TimeNIC. GM + client .12.
- **ptp-ocp-gnsspps** — the TAP PTM-capable `ptp_ocp` plus the raw-GNSS-PPS
  patch. **Required**: the Time Card runs a PTM FPGA image the stock in-tree
  driver cannot drive (all-ones registers, wedged udev — looks exactly like
  dead hardware). Stock `ptp_ocp` is blacklisted; `ptp_ocp-load.service`
  loads the DKMS build at boot and refuses to load a stock module. GM only.
  See `ptp-ocp-gnsspps/README.md`, including the devlink-flash/SPI caveat.

After a kernel upgrade, check that the *running* modules match the on-disk
DKMS builds (the deploy warns when they don't): a reboot that regenerates
initramfs ordering wrong can silently boot the stock drivers.

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
