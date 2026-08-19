# ptp_ocp GNSS PPS fix for the OCP Time Card

Driver change for the grandmaster so the Time Card's kernel PPS device
(`/dev/ppsN`, symlinked to `/dev/pps-timecard` by `files/timecard-ptp.rules`)
carries the **raw GNSS receiver 1PPS** instead of the disciplined FPGA PPS.
gpsd consumes that device (RFC 2783), which lights up the PPS panels of the
gpsd-prometheus-exporter Grafana dashboard with true receiver-pulse semantics:
asserts stop when the receiver stops pulsing, instead of free-running on the
disciplined clock through a GNSS outage.

**Installation is automated** by `tasks/ptp-ocp-gnsspps.yml` in the main
deployment (gated by `ptp_ocp_gnsspps_enabled` in `group_vars/ptp_server.yml`):
Ansible copies `dkms/` to `/opt/ptp-ocp-gnsspps`, runs `dkms add`/`dkms install`
for the running kernel, ships `/etc/modprobe.d/ptp_ocp-gnsspps.conf`
(`options ptp_ocp gnss_pps=1`), rebuilds the initramfs, and flags
`/run/reboot-required` when the running module differs from the installed one.
It follows the igc-ppsfix convention of never reloading the module live —
chrony, ts2phc and gpsd all hold the Time Card open — though unlike igc a
manual reload is *possible* (ptp_ocp does not carry the SSH session): stop
chrony/ts2phc/gpsd, `modprobe -r ptp_ocp && modprobe ptp_ocp`, start them again.

## Why the stock driver can't do this

The stock `ptp_ocp` has two disjoint kernel paths for the two pulses:

- The **raw GNSS PPS** is hardware-timestamped by the FPGA's dedicated
  timestamper (`TC_Timestamper_Gnss1Pps`, driver resource `ts0`) and delivered
  only as `PTP_CLOCK_EXTTS` channel-0 events on the PHC character device.
  gpsd cannot read PHC extts events.
- The **kernel PPS device** (registered because `ptp_ocp_clock_info.pps = true`)
  is fed only from the FPGA-PPS timestamper's interrupt (`bp->pps`, resource at
  0x010C0000): `ptp_ocp_ts_irq()` emits `PTP_CLOCK_PPS` only when
  `ext == bp->pps`.

Both timestampers share the same IRQ handler and enable function — the driver
simply never emits the PPS event type from `ts0`. That is the whole fix.

## The change (see `patches/ptp-ocp-gnsspps-7.0.patch`)

A `gnss_pps` module parameter (bool, default 0 = stock behavior) and a
`ptp_ocp_pps_source(bp)` helper returning `bp->ts0` when set, `bp->pps`
otherwise, substituted at the three sites that select the kernel-PPS
timestamper:

1. `ptp_ocp_enable()` `PTP_CLK_REQ_PPS`: `PTP_ENABLE_PPS` arms the GNSS
   timestamper's IRQ.
2. `ptp_ocp_ts_irq()`: each raw GNSS pulse emits `PTP_CLOCK_PPS` → `/dev/ppsN`
   assert (timestamped by the system clock at IRQ time, as before).
3. `ptp_ocp_ts_enable()`: the existing kernel-PPS/extts sharing bookkeeping
   (`pps_req_map`) follows the selected timestamper, so PHC extts channel-0
   users (e.g. a chrony `extpps` refclock) coexist with the kernel PPS.

Unchanged on purpose:

- extts channel 5 stays mapped to the FPGA-PPS timestamper (it degrades to a
  plain non-shared timestamper, like TS1-TS4).
- The debugfs summary (`TS5` row) still reports the PPS request state against
  the FPGA-PPS timestamper — cosmetic only.
- ts2phc/ptp4l/chrony are unaffected: nothing in that chain uses the kernel
  PPS device.

`dkms/src/ptp_ocp.c` is the clean v7.0 mainline source with the patch applied
(same convention as igc-ppsfix). PPS events only flow after `PTP_ENABLE_PPS`
is issued on the PHC — `templates/timecard/timecard-sma.sh.j2` does that at
boot (gated by `timecard_kernel_pps`); the request persists until the module
unloads.

## Behavior notes

- With `gnss_pps=1` and the GNSS antenna pulled, `/dev/pps-timecard` asserts
  stop (or degrade) according to the receiver's timepulse configuration
  (u-blox UBX-CFG-TP5) — the receiver may be configured to keep pulsing from
  its internal oscillator when unlocked. Verify with `ubxtool` if exact
  loss-of-lock behavior matters.
- PPS assert timestamps are system-clock-at-IRQ, so the measurement carries
  µs-class interrupt latency — fine for the gpsd dashboard, not a substitute
  for the hardware timestamps on extts channel 0.
