#!/bin/bash
# Print the TMP117 temperature in degrees C. With an interval argument
# (seconds, may be fractional) keep printing one timestamped line per
# interval until interrupted.
#
#   tmp117.sh          -> 34.1953
#   tmp117.sh 1        -> 2026-09-05T10:00:00 34.1953  (repeating)
#
# Reads the IIO device the tmp117 kernel driver exposes (instantiated at
# boot by tmp117-i2c.service). Raw LSB is 7.8125 mC; scale is read from
# sysfs rather than hardcoded.
set -euo pipefail

dev=""
for d in /sys/bus/iio/devices/iio:device*; do
    [ -r "$d/name" ] && [ "$(cat "$d/name")" = "tmp117" ] && dev="$d" && break
done
if [ -z "$dev" ]; then
    echo "tmp117.sh: no tmp117 IIO device (is tmp117-i2c.service running?)" >&2
    exit 1
fi

read_temp() {
    local raw scale
    raw=$(cat "$dev/in_temp_raw")
    scale=$(cat "$dev/in_temp_scale")
    # scale is in milli-degrees per LSB
    awk -v r="$raw" -v s="$scale" 'BEGIN { printf "%.4f\n", r * s / 1000 }'
}

if [ $# -eq 0 ]; then
    read_temp
    exit 0
fi

interval="$1"
while true; do
    printf '%s %s\n' "$(date +%Y-%m-%dT%H:%M:%S)" "$(read_temp)"
    sleep "$interval"
done
