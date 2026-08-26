#!/usr/bin/env bash
# Managed by Ansible (roles/tgpio_pps).
# pps_gen_tio latches OFF permanently after a single missed comparator
# event ("Event missed, Disabling Timed I/O" -- seen 2026-08-25 after
# ~70 min of clean output; one-shot SMI/latency stalls are enough) and
# nothing re-arms it (boot arming is a oneshot in tgpio-pps-arm.service).
# Follow the kernel journal and re-arm every pps-gen when the driver
# disables one; worst case is a 1-2 s gap in the 1PPS instead of a
# permanent outage.
#
# CAVEAT: the driver toggles the pad with no notion of absolute level, so
# a re-arm from a frozen pin is a 50/50 phase coin flip -- the rising edge
# lands on x.0 or x.5. After any re-arm logged here, check the TICC; a
# steady 0.5 s offset means inverted (fix: disable at x.25, re-enable).
# Only a pps_gen_tio patch to explicit per-event edge polarity removes this.
set -u

journalctl -kf -n 0 --output=cat | while read -r line; do
  case "$line" in
    *"Disabling Timed I/O"*)
      sleep 1  # let the driver finish its disable path before re-arming
      for gen in /sys/class/pps-gen/*/enable; do
        [ -e "$gen" ] || continue
        if echo 1 > "$gen" 2>/dev/null; then
          logger -t tgpio-pps-watch "re-armed ${gen%/enable} after driver self-disable"
        else
          logger -t tgpio-pps-watch "FAILED to re-arm ${gen%/enable}"
        fi
      done
      ;;
  esac
done
