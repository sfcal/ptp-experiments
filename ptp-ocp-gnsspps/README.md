# ptp_ocp driver for the OCP Time Card (TAP PTM driver + GNSS PPS patch)

The grandmaster's Time Card runs a **PTM FPGA image**, and the stock in-tree
`ptp_ocp` driver cannot drive it: every fabric register reads all-ones
(`Version 255.255.65535`, devlink `fw 255.32767`), EEPROM reads fail, SMA
sysfs writes return EOPNOTSUPP — and loading it deterministically wedges udev
(a udev-worker hangs D-state in the spi-nor probe holding a mutex; only a
reboot clears it). This looks exactly like dead hardware and was misdiagnosed
as such twice (2026-08-14 and 2026-08-19).

`dkms/src/ptp_ocp.c` is therefore the **Time-Appliances-Project driver**
(`Time-Card` repo `DRV/Linux`, commit `1042bd6f`) with three local changes:

1. `patches/tap-ptm-compat-7.0.patch` — two build fixes for the 7.0 kernel:
   a `RHEL_RELEASE_CODE`/`RHEL_RELEASE_VERSION` stub (the repo's compat
   guards are a hard preprocessor error on non-RHEL kernels), and the
   two-arg `pci_enable_ptm(bp->pdev, NULL)` form.
2. `patches/gnsspps-on-tap-driver.patch` — the `gnss_pps` raw-PPS parameter
   (below), ported from the old mainline-based build.

**Installation is automated** by the `dkms_module` role in `deploy.yml`
(gated by `ptp_ocp_gnsspps_enabled`): DKMS install, initramfs rebuild, and
`/run/reboot-required` when the running module differs — plus two pieces
specific to this module:

- `blacklist ptp_ocp` in `/etc/modprobe.d/ptp_ocp-gnsspps.conf`: the stock
  driver must never autoload against the PTM image.
- `ptp_ocp-load.service`: loads the module explicitly at boot, ordered
  before timecard-sma/chrony/gpsd/ts2phc/ptp4l — and refuses (harmlessly)
  if the on-disk module would resolve to the stock driver, e.g. in a
  kernel-upgrade window before DKMS has rebuilt.

Known limitation: under the PTM image the FPGA's SPI NOR never probes (the
flash IRQ appears unserviced), so `devlink dev flash` does not work and MTD
is absent. Do not unbind/rebind `spi-nor` on `spi2048.0` to retry — it only
adds D-state tasks. Reflashing the card is a JTAG job.

## The gnss_pps patch

Makes the Time Card's kernel PPS device (`/dev/ppsN`, symlinked to
`/dev/pps-timecard` by the timecard role's udev rules) carry the **raw GNSS
receiver 1PPS** instead of the disciplined FPGA PPS. gpsd consumes that
device (RFC 2783), which lights up the PPS panels of the
gpsd-prometheus-exporter dashboard with true receiver-pulse semantics:
asserts stop when the receiver stops pulsing, instead of free-running on the
disciplined clock through a GNSS outage.

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

## The change (see `patches/gnsspps-on-tap-driver.patch`)

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

PPS events only flow after `PTP_ENABLE_PPS` is issued on the PHC —
`roles/timecard/templates/timecard-sma.sh.j2` does that at boot (gated by
`timecard_kernel_pps`); the request persists until the module unloads.

## Behavior notes

- With `gnss_pps=1` and the GNSS antenna pulled, `/dev/pps-timecard` asserts
  stop (or degrade) according to the receiver's timepulse configuration
  (u-blox UBX-CFG-TP5) — the receiver may be configured to keep pulsing from
  its internal oscillator when unlocked. Verify with `ubxtool` if exact
  loss-of-lock behavior matters.
- PPS assert timestamps are system-clock-at-IRQ, so the measurement carries
  µs-class interrupt latency — fine for the gpsd dashboard, not a substitute
  for the hardware timestamps on extts channel 0.
