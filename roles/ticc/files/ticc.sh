#!/bin/bash
# Managed by Ansible (roles/ticc). Remote control for TICC captures:
#   ticc.sh start <name> | stop | reset | status | ls
set -euo pipefail

dir=/var/log/ticc

die() { echo "ticc.sh: $*" >&2; exit 1; }

# The active ticc-capture@ instance, if any. One TICC, one reader: two
# processes on the same port would round-robin-steal bytes.
active() {
    systemctl list-units --plain --no-legend --state=active 'ticc-capture@*.service' | awk '{print $1}'
}

newest() { ls -t "$dir"/*.log 2>/dev/null | head -n 1 || true; }

case ${1:-} in
    start)
        name=${2:-}
        [[ -n $name ]] || die "usage: ticc.sh start <name>"
        [[ $name =~ ^[A-Za-z0-9._-]+$ ]] || die "name must match [A-Za-z0-9._-]+"
        [[ -e /dev/ticc ]] || die "/dev/ticc missing -- TICC unplugged?"
        a=$(active)
        [[ -z $a ]] || die "already capturing ($a) -- ticc.sh stop first"
        systemctl start "ticc-capture@$name"
        sleep 1
        if ! systemctl is-active --quiet "ticc-capture@$name"; then
            systemctl --no-pager -l status "ticc-capture@$name" >&2 || true
            die "capture failed to start"
        fi
        echo "capturing to $(newest)"
        ;;
    stop)
        a=$(active)
        [[ -n $a ]] || { echo "no capture running"; exit 0; }
        systemctl stop "$a"
        echo "stopped $a"
        f=$(newest)
        [[ -z $f ]] || ls -l "$f"
        ;;
    reset)
        a=$(active)
        if [[ -n $a ]]; then
            # Reopening the port pulses DTR; the worker rolls a new file.
            systemctl restart "$a"
            sleep 1
            echo "TICC reset; capturing to $(newest)"
        else
            [[ -e /dev/ticc ]] || die "/dev/ticc missing -- TICC unplugged?"
            : < /dev/ticc
            echo "TICC reset"
        fi
        ;;
    status)
        a=$(active)
        echo "capture: ${a:-none}"
        failed=$(systemctl list-units --plain --no-legend --state=failed 'ticc-capture@*.service' | awk '{print $1}')
        [[ -n $failed ]] && echo "failed: $failed (see journalctl -u ...)"
        f=$(newest)
        if [[ -n $f ]]; then
            ls -l "$f"
            tail -n 3 "$f"
        fi
        ;;
    ls)
        ls -lt "$dir"
        ;;
    *)
        die "usage: ticc.sh start <name> | stop | reset | status | ls"
        ;;
esac
