#!/usr/bin/env bash
# Managed by Ansible (roles/tgpio_pps).
# Arm the TGPIO 1PPS generators once, after chrony has finished its boot
# steps. Arming earlier (the old udev-add rule) always lost the race with
# the +-37 s TAI/UTC startup steps: a step past the pending comparator
# makes pps_gen_tio disable itself ("Event missed"), and the watch's
# re-arm then restarts the toggle from a frozen pin level -- a 50/50 phase
# coin flip that shows up as a rock-stable 0.5 s offset on the TICC.
# Armed from the pad's reset-low state with no step coming, the first
# toggle is a rising edge on a full second: phase correct by construction.
set -u

# pps_gen_tio autoloads from the ACPI modalias early in boot; give the
# device a minute to appear.
for _ in $(seq 60); do
  compgen -G "/sys/class/pps-gen/*/enable" > /dev/null && break
  sleep 1
done

# Synchronized with residual correction < 10 ms: from there chrony only
# slews, which the driver's per-edge scheduling follows fine; only a step
# larger than its 10 ms guard time kills the comparator.
if ! chronyc waitsync 120 0.01 0 2 > /dev/null; then
  logger -t tgpio-pps-arm "chronyc waitsync gave up after 4 min; arming anyway"
fi

armed=0
for gen in /sys/class/pps-gen/*/enable; do
  [ -e "$gen" ] || continue
  if echo 1 > "$gen" 2>/dev/null; then
    logger -t tgpio-pps-arm "armed ${gen%/enable} after time sync"
    armed=1
  else
    logger -t tgpio-pps-arm "FAILED to arm ${gen%/enable}"
  fi
done
[ "$armed" -eq 1 ]
