#!/bin/bash
# Managed by Ansible (roles/ticc). Capture worker for ticc-capture@.service.
# One timestamped file per run; append-only, so nothing is ever overwritten.
# Measurement lines are "<reading>\t<ISO 8601 GPS time>": the merger below
# tags each TICC line with the latest gpsd ZDA second.
set -euo pipefail

log=/var/log/ticc/${1:?usage: ticc-capture.sh <name>}_$(date +%Y%m%d-%H%M%S).log

# Single open shared by stty and the reader: the open's DTR pulse reboots the
# TICC, so each log starts with its config banner. raw + -echo: never write
# back to the port (stray bytes would hit the TICC's config parser).
exec < /dev/ticc
stty 115200 raw -echo

# Two producers feed one merger through a pipe. Each producer emits whole
# lines and flushes per line -- short pipe writes are atomic, so lines never
# splice. (cat would forward partial reads; that's why the TICC side is awk.)
{
    # GPS wall-clock: one ISO 8601 line per new ZDA second. If gpsd dies the
    # capture carries on; the merger just keeps re-using the last anchor,
    # which shows up as repeated timestamps.
    gpspipe -r | awk -F, '/^\$G.ZDA/ {t=$5"-"$4"-"$3"T"substr($2,1,2)":"substr($2,3,2)":"substr($2,5)"Z"; if (t!=p) {print t; fflush()} p=t}' &

    # The TICC streams whenever powered, and its already-sent bytes (buffered
    # in the USB bridge, which the DTR reset does not clear) are delivered
    # right after the open -- a stale, possibly truncated tail of the previous
    # run. Drop everything until the boot banner so the log, and the analysis,
    # start clean.
    rc=0
    awk '!p && /^#/ {p=1} p {print; fflush()}' || rc=$?    # the TICC stream
    # TICC gone: kill the GPS side (gpspipe follows via SIGPIPE) so the
    # merger sees EOF and the unit goes down visibly, per Restart=no.
    kill "$!" 2>/dev/null || true
    exit "$rc"
} | awk '
    /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T/ { ts = $0; next }
    {
        sub(/\r$/, "")
        # Tag only measurement-shaped lines; the config banner stays as-is.
        if (ts != "" && $0 ~ /^[ \t]*[-+.0-9]/) print $0 "\t" ts
        else print
        fflush()
    }
' >> "$log"
