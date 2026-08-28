# igc PPS fix for the TimeNIC (Intel I226)

Driver fix for the grandmaster, so ts2phc can discipline the NIC PHC from
the Timecard's 1PPS with hardware edge timestamping instead of a software
PHC-to-PHC copy through the system clock's oscillator.

**The install is automated** by this role in the main deployment
(gated by `igc_ppsfix_enabled` in `group_vars/server.yml`): Ansible copies
`files/src/` to `/usr/local/src/igc-ppsfix`, runs `./remake install`
(build + install to `/lib/modules/<kver>/updates/igc.ko` + depmod — same
pattern as `roles/timecard` for ptp_ocp), rebuilds the initramfs, and flags
deploy.yml's shared reboot task when the running module differs from the
on-disk one. A leftover DKMS igc install would shadow the module (depmod
searches `updates/dkms` before `updates`), so the role asserts none is
present rather than cleaning one up. It never reloads the module live
(enp1s0 is the igc NIC carrying the SSH session). The build tree is fully
standalone — the manual steps below still work as-is.

The stock igc driver — verified unchanged through mainline v7.0/v7.1 —
cannot do PPS properly on the I225/I226:

1. **EXTTS (PPS input):** the hardware timestamps *both* signal edges and
   the driver rejects rising-edge-only requests (`PTP_STRICT_FLAGS` demands
   both edges), so every GPS-style PPS produces a spurious falling-edge
   event and ts2phc misbehaves even with `extts_polarity both` workarounds.
2. **PEROUT (PPS output):** a 1 s period (half-period 500000000 ns) is
   routed into frequency mode, giving a free-running 1 Hz square wave not
   aligned to the PHC second boundary.
3. **No EXTTS channel state:** `struct igc_adapter` doesn't track which SDP
   pin / flags each EXTTS channel uses, so an interrupt-time edge filter has
   nothing to consult.
4. **GPIO propagation delay:** the I226's internal GPIO read lags the edge
   interrupt, so a naive pin-state read can see the wrong level.

The fix (ported from Time-Appliances-Project TimeHAT "ppsfix", rebased onto
clean upstream source):

- Forces rising-edge-only EXTTS and filters wrong-edge events in the
  interrupt handler by sampling the SDP pin level (fixes 1).
- Removes `500000000` from the frequency-mode list so 1PPS output uses
  target-time mode, aligned to the PHC top of second (fixes 2).
- Adds `ts0_pin/ts0_flags/ts1_pin/ts1_flags` to `igc_adapter`, recorded at
  EXTTS enable time and consumed by the filter (fixes 3).
- Module params for the filter, runtime-tunable via
  `/sys/module/igc/parameters/` (fixes 4):
  - `edge_check_delay_us` (default 20) — µs to wait before sampling the pin
  - `edge_check_invert` (default 0) — set 1 if all events get skipped
    (some I226 units report the inverted level)

## Layout

```
files/src/                   mainline v7.0 igc + fix applied, self-contained
                             out-of-tree build (Makefile + remake script)
files/patches/igc-ppsfix-7.0.patch
                             same fix as a patch against kernel 7.0 source
                             (provenance; `patch -p1` it into a kernel tree
                             if you ever build the fix in-tree instead)
```

## Manual build (Ubuntu 7.0.0-x-generic, e.g. the grandmaster)

```bash
sudo apt install -y build-essential linux-headers-$(uname -r)
scp -r roles/igc_ppsfix/files/src time:~/igc-src   # or however you copy it
ssh time
cd ~/igc-src
sudo ./remake install
sudo update-initramfs -u -k $(uname -r)
sudo reboot
```

`remake install` puts the module at `/lib/modules/<ver>/updates/igc.ko`,
which depmod prefers over the in-tree driver, and runs depmod. The
initramfs rebuild matters: igc is the boot NIC's driver and loads from the
initramfs, so without it the stock module stays live even after a reboot.
Unlike DKMS there is no automatic rebuild on kernel package updates — a
new kernel runs the stock driver (NIC fine, PPS fix absent) until the next
deploy run rebuilds for it. Verify which module is live:

```bash
modinfo igc | grep -E 'filename|edge_check'
```

`filename` must point at `updates/igc.ko` (not `updates/dkms/` — that
would be a leftover DKMS install shadowing this one) and the two
`edge_check` params must be listed.

**Rollback:** `sudo rm /lib/modules/$(uname -r)/updates/igc.ko &&
sudo depmod -a && sudo update-initramfs -u -k $(uname -r) && sudo reboot`
— the untouched in-tree module takes over again.

Notes: the source is mainline v7.0; it has not been compile-tested against
Ubuntu's 7.0 headers yet, so watch the first `remake install`. The module
is unsigned — do not port this pattern to a Secure Boot host (MOK signing
was the one thing the old DKMS route did that remake does not); at boot a
preferred-but-rejected unsigned igc would leave the machine without its
NIC.

## Testing on the TimeNIC

With an SMA loopback cable between the two connectors:

```bash
sudo testptp -d /dev/ptp0 -L0,2          # SDP0 -> periodic output
sudo testptp -d /dev/ptp0 -p 1000000000  # aligned 1PPS out
sudo testptp -d /dev/ptp0 -L1,1          # SDP1 -> external timestamp input
sudo testptp -d /dev/ptp0 -e 5           # expect 1 event/s, stable nanoseconds
```

Then with the Timecard's PPS OUT cabled to the TimeNIC's PPS IN:

```bash
sudo ts2phc -c /dev/ptp0 -s generic --ts2phc.pin_index 1 -l 7 -m
```

No `--ts2phc.extts_polarity both` / `--ts2phc.pulsewidth` workarounds are
needed with this driver. If every event is skipped, flip
`edge_check_invert`; if offsets jitter by a fixed amount, tune
`edge_check_delay_us`:

```bash
echo 1 | sudo tee /sys/module/igc/parameters/edge_check_invert
```

Caveat: ts2phc's `generic` source only aligns the second edge — coarse-set
the NIC PHC first (within ±0.5 s; the ts2phc unit's ExecStartPre does this
from the Timecard) so the seconds are numbered correctly.

## Provenance / license

Driver base: `drivers/net/ethernet/intel/igc/` from mainline Linux v7.0
(git.kernel.org), GPL-2.0. PPS changes extracted from
[Time-Appliances-Project/TimeHAT](https://github.com/Time-Appliances-Project/TimeHAT)
`intel-igc-ppsfix_rpi5_6.12.62.zip` by diffing against upstream 6.12.62
(base-version skew discarded), then rebased onto v7.0 and 6.12.47.
