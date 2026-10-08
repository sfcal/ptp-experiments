#!/usr/bin/env python3
# Managed by Ansible (roles/ntpheat).
#
# ntpheat: hold the CPU package temperature at a setpoint by burning idle
# cycles, so the crystal that clocks the system clock stops following room
# temperature. A Python 3 rewrite of the Raspberry Pi ntpheat
# (https://www.satsignal.eu/ntp/Raspberry-Pi-ntpheat.html), with two
# changes:
#
#  * The sensor is chosen by thermal-zone type, not hard-coded zone0 (on
#    the LattePanda Mu, zone0 is the ACPI board sensor at ~28 C and zone1
#    is x86_pkg_temp), or with --iio-name an IIO temperature device such
#    as the TMP117 (roles/ntpheat/tasks/tmp117.yml) wired next to the oscillator: +/-0.1 C
#    absolute, 7.8 mC resolution, and it reads the thing we actually care
#    about instead of the die hotspot. It converts once a second, so with
#    IIO the controller samples at 4 Hz instead of 20.
#  * --blend-weight W adds W times a second thermal zone (default
#    x86_pkg_temp) to the regulated temperature. The GM's system-clock
#    frequency fits -0.05 ppm/C of package plus -0.22 ppm/C of board
#    (TMP117/NVMe), so holding either sensor alone leaves the other term
#    free: 0.75 ppm/day with the package pinned at 62 C (2026-09-05),
#    0.59 ppm/day with the TMP117 pinned at 48.5 C (2026-09-06, the loop
#    swung the package 67 -> 56 C to do it). Holding tmp117 + 0.2*pkg
#    holds the frequency to first order, and the package's 14 C/duty
#    lifts the heater's authority from ~5 to ~8 C per unit duty.
#  * The original bang-bang loop is replaced by a PI controller on the
#    burn duty cycle. The burners PWM in short --slot windows (50 ms:
#    on for duty*slot, off for the rest), and the controller averages the
#    sensor at 20 Hz over each --period before nudging the duty. Both
#    matter: x86_pkg_temp is the die hotspot and moves ~10 C within a
#    0.4 s burst at 1.6 GHz, so 1 s PWM plus a single read per period had
#    the P term slamming the duty around by burst phase (2026-09-04:
#    measured 20% actual vs 40% reported duty). Averaging also turns the
#    sensor's 1 C steps into a usable sub-degree signal.
#
#  * The default heat source is `openssl speed` on AES-256-GCM, duty-cycled
#    with SIGSTOP/SIGCONT. On the GM's fixed-800 MHz N100 that draws ~50%
#    more per core than a Python hash loop (measured 2026-09-04 over a
#    3.5 W idle: +1.46 W for 4 AES burners vs +0.95 W for 4 md5 loops, with
#    SHA-256 and an AVX2 FMA loop both lower still). --burner python keeps
#    the original in-process md5 loop for hosts without openssl.
#
# Run it under SCHED_IDLE / nice 19 (the systemd unit does): the heater
# must only ever take cycles nobody else wants.
import argparse
import hashlib
import multiprocessing
import os
import shutil
import signal
import subprocess
import sys
import time

THERMAL = "/sys/class/thermal"
IIO = "/sys/bus/iio/devices"


def find_sensor(zone_type):
    """Path of the thermal zone whose 'type' matches, or None."""
    try:
        zones = sorted(os.listdir(THERMAL))
    except FileNotFoundError:
        return None
    for z in zones:
        if not z.startswith("thermal_zone"):
            continue
        try:
            with open(os.path.join(THERMAL, z, "type")) as f:
                if f.read().strip() == zone_type:
                    return os.path.join(THERMAL, z, "temp")
        except OSError:
            continue
    return None


def find_iio(name):
    """in_temp_raw path of the IIO device whose 'name' matches, or None."""
    try:
        devs = sorted(os.listdir(IIO))
    except FileNotFoundError:
        return None
    for d in devs:
        try:
            with open(os.path.join(IIO, d, "name")) as f:
                if f.read().strip() == name:
                    return os.path.join(IIO, d, "in_temp_raw")
        except OSError:
            continue
    return None


def is_iio(path):
    return os.path.basename(path) == "in_temp_raw"


def make_reader(path):
    """Callable returning the sensor in degrees C. Thermal zones report
    millidegrees; an IIO in_temp_raw is in LSBs of the sibling in_temp_scale
    (milli-degrees per LSB, 7.8125 for the TMP117)."""
    if is_iio(path):
        with open(os.path.join(os.path.dirname(path), "in_temp_scale")) as f:
            scale = float(f.read().strip()) / 1000.0
    else:
        scale = 0.001

    def read():
        with open(path) as f:
            return int(f.read().strip()) * scale
    return read


def burner_python(duty, slot):
    """Burn for duty*slot seconds out of every slot, forever."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    md5 = hashlib.md5()
    chunk = b"Nobody inspects the spammish repetition"
    while True:
        start = time.monotonic()
        stop = start + duty.value * slot
        while time.monotonic() < stop:
            for _ in range(200):
                md5.update(chunk)
        rest = start + slot - time.monotonic()
        if rest > 0:
            time.sleep(rest)


# Runs AES-256-GCM on 8 KiB blocks essentially forever (-seconds is wall
# time via alarm(), so time spent SIGSTOPped counts; 2e9 s is 63 years).
OPENSSL_CMD = ["openssl", "speed", "-seconds", "2000000000", "-bytes", "8192",
               "-evp", "aes-256-gcm"]


def burner_openssl(duty, slot):
    """Duty-cycle an `openssl speed` child with SIGSTOP/SIGCONT per slot."""
    proc = None

    def stop(*_):
        if proc is not None and proc.poll() is None:
            # A stopped process ignores SIGTERM until continued.
            proc.send_signal(signal.SIGCONT)
            proc.terminate()
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)

    while True:
        if proc is None or proc.poll() is not None:
            proc = subprocess.Popen(OPENSSL_CMD, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        start = time.monotonic()
        on = duty.value * slot
        if on > 0:
            proc.send_signal(signal.SIGCONT)
            time.sleep(on)
        if on < slot:
            proc.send_signal(signal.SIGSTOP)
            rest = start + slot - time.monotonic()
            if rest > 0:
                time.sleep(rest)


def write_metrics(path, temp, target, duty, copies, sensors=(), blend_weight=0.0):
    """Atomically replace the node_exporter textfile. `sensors` is a list of
    (name, reading) for the individual sensors behind a blended `temp`."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("# HELP ntpheat_temp_celsius Temperature ntpheat is regulating (its chosen sensor, "
                "or primary + blend_weight * secondary when blending).\n")
        f.write("# TYPE ntpheat_temp_celsius gauge\n")
        f.write(f"ntpheat_temp_celsius {temp:.3f}\n")
        if sensors:
            f.write("# HELP ntpheat_sensor_celsius Individual sensor readings behind ntpheat_temp_celsius.\n")
            f.write("# TYPE ntpheat_sensor_celsius gauge\n")
            for name, value in sensors:
                f.write(f'ntpheat_sensor_celsius{{sensor="{name}"}} {value:.3f}\n')
            f.write("# HELP ntpheat_blend_weight Weight of the secondary sensor in ntpheat_temp_celsius.\n")
            f.write("# TYPE ntpheat_blend_weight gauge\n")
            f.write(f"ntpheat_blend_weight {blend_weight:.4f}\n")
        f.write("# HELP ntpheat_target_celsius ntpheat setpoint.\n")
        f.write("# TYPE ntpheat_target_celsius gauge\n")
        f.write(f"ntpheat_target_celsius {target:.3f}\n")
        f.write("# HELP ntpheat_duty_ratio Fraction of each period the burners run (0 = off, 1 = saturated).\n")
        f.write("# TYPE ntpheat_duty_ratio gauge\n")
        f.write(f"ntpheat_duty_ratio {duty:.4f}\n")
        f.write("# HELP ntpheat_copies Number of burner processes.\n")
        f.write("# TYPE ntpheat_copies gauge\n")
        f.write(f"ntpheat_copies {copies}\n")
    os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser(description="hold the CPU temperature at a setpoint by burning idle cycles")
    p.add_argument("-t", "--temp", type=float, default=60.0, help="setpoint, degrees C (default 60)")
    p.add_argument("-c", "--copies", type=int, default=1, help="burner processes (default 1)")
    p.add_argument("--zone-type", default="x86_pkg_temp",
                   help="/sys/class/thermal zone type to read (default x86_pkg_temp)")
    p.add_argument("--iio-name", default="",
                   help="IIO device name to read instead (e.g. tmp117); overrides --zone-type")
    p.add_argument("--sensor", default="",
                   help="explicit temp file (thermal zone temp or IIO in_temp_raw); overrides both")
    p.add_argument("--blend-zone-type", default="x86_pkg_temp",
                   help="second /sys/class/thermal zone type to blend in (default x86_pkg_temp)")
    p.add_argument("--blend-weight", type=float, default=0.0,
                   help="regulate primary + W * blend zone instead of the primary alone "
                        "(default 0 = off; the GM uses 0.2 with tmp117 primary, see header)")
    p.add_argument("--period", type=float, default=1.0, help="control period, seconds (default 1)")
    p.add_argument("--slot", type=float, default=0.05,
                   help="burner PWM slot, seconds (default 0.05)")
    p.add_argument("--kp", type=float, default=0.02, help="proportional gain, duty per degree (default 0.02)")
    p.add_argument("--ki", type=float, default=0.002,
                   help="integral gain, duty per degree-second (default 0.002)")
    p.add_argument("--metrics", default="",
                   help="node_exporter textfile to write (default: none)")
    p.add_argument("--metrics-interval", type=float, default=10.0,
                   help="seconds between metrics writes (default 10)")
    p.add_argument("--burner", choices=["openssl", "python"], default="openssl",
                   help="heat source: openssl speed AES-256-GCM child (default) or an "
                        "in-process md5 loop")
    p.add_argument("--probe", action="store_true",
                   help="print the chosen sensor and its reading, then exit")
    p.add_argument("--duty", type=float, default=None,
                   help="open loop: hold this fixed burner duty (0..1) instead of regulating; "
                        "for step tests when tuning (metrics still written)")
    args = p.parse_args()

    # At boot the x86_pkg_temp zone appears a few seconds after this unit
    # starts (seen 2026-09-04: exit 1, restarted by systemd 10 s later), and
    # an IIO sensor only exists once its instantiation unit has run, so
    # wait for the sensor rather than fail.
    deadline = time.monotonic() + 120
    while True:
        if args.sensor:
            sensor = args.sensor
        elif args.iio_name:
            sensor = find_iio(args.iio_name)
        else:
            sensor = find_sensor(args.zone_type)
        blend = find_sensor(args.blend_zone_type) if args.blend_weight else None
        try:
            if sensor and (blend or not args.blend_weight):
                read_temp = make_reader(sensor)
                temp = read_temp()
                read_blend = make_reader(blend) if blend else None
                blend_temp = read_blend() if blend else None
                break
            if sensor:
                err = f"no thermal zone of type {args.blend_zone_type!r} under {THERMAL} to blend"
            elif args.iio_name:
                err = f"no IIO device named {args.iio_name!r} under {IIO}"
            else:
                err = f"no thermal zone of type {args.zone_type!r} under {THERMAL}"
        except (OSError, ValueError) as e:
            err = f"cannot read {sensor} / {blend}: {e}"
        if args.probe or time.monotonic() > deadline:
            sys.exit(f"ntpheat: {err}")
        time.sleep(2)
    if args.burner == "openssl" and not shutil.which("openssl"):
        sys.exit("ntpheat: openssl not found; install it or use --burner python")
    if args.sensor:
        sensor_name = os.path.basename(os.path.dirname(sensor)) if is_iio(sensor) else sensor
    else:
        sensor_name = args.iio_name or args.zone_type
    if read_blend:
        print(f"ntpheat: sensor {sensor} reads {temp:.2f} C + {args.blend_weight} x {blend} "
              f"at {blend_temp:.2f} C = {temp + args.blend_weight * blend_temp:.2f} C, "
              f"setpoint {args.temp:.1f} C, {args.copies} {args.burner} burner(s)", flush=True)
    else:
        print(f"ntpheat: sensor {sensor} reads {temp:.2f} C, setpoint {args.temp:.1f} C, "
              f"{args.copies} {args.burner} burner(s)", flush=True)
    if args.probe:
        return
    if args.copies < 1:
        sys.exit("ntpheat: --copies must be >= 1")
    burn = burner_openssl if args.burner == "openssl" else burner_python

    # Plain fork: no threads here, and it keeps the burners' cmdline
    # readable as ntpheat.py (3.14's forkserver default hides it).
    if "fork" in multiprocessing.get_all_start_methods():
        multiprocessing.set_start_method("fork")
    duty = multiprocessing.Value("d", 0.0)
    workers = [multiprocessing.Process(target=burn, args=(duty, args.slot), daemon=True)
               for _ in range(args.copies)]
    for w in workers:
        w.start()

    def stop(*_):
        for w in workers:
            w.terminate()
        for w in workers:
            w.join(5)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    # PI controller on the period-averaged temperature. err > 0 means too
    # cold -> more duty. Positional form, duty = kp*err + integral, with the
    # integral clamped to the duty range as anti-windup. (The earlier
    # velocity form, d += ki*err*dt + kp*d(err), misbehaves against the
    # output clamp: while pinned at 0 above the setpoint, a falling error
    # still adds kp*d(err) each period, so the heater ran at a few percent
    # while 2 C too warm. Harmless at kp 0.02, not at the TMP117's kp 0.4.)
    d = 0.0
    integ = 0.0
    if args.duty is not None:
        d = min(1.0, max(0.0, args.duty))
        duty.value = d
        print(f"ntpheat: open loop, fixed duty {d:.3f}", flush=True)
    last_metrics = 0.0
    # 20 Hz for the package sensor (see the header); an IIO sensor like the
    # TMP117 converts once a second, so 4 Hz is plenty and spares the I2C bus.
    sample_dt = 0.25 if is_iio(sensor) else 0.05
    # The blend zone is the package sensor and needs the full 20 Hz
    # averaging; the primary keeps its own rate (every `stride` ticks).
    tick = 0.05 if read_blend else sample_dt
    stride = max(1, round(sample_dt / tick))
    sensors = ()
    while True:
        # Average the sensor over the whole period: the package sensor is
        # the die hotspot and ripples with the PWM, and it only steps in
        # whole degrees.
        acc, n = 0.0, 0
        bacc, bn = 0.0, 0
        t_end = time.monotonic() + args.period
        i = 0
        while True:
            if i % stride == 0:
                try:
                    acc += read_temp()
                    n += 1
                except (OSError, ValueError) as e:
                    print(f"ntpheat: read failed: {e}", file=sys.stderr, flush=True)
            if read_blend:
                try:
                    bacc += read_blend()
                    bn += 1
                except (OSError, ValueError) as e:
                    print(f"ntpheat: blend read failed: {e}", file=sys.stderr, flush=True)
            i += 1
            left = t_end - time.monotonic()
            if left <= 0:
                break
            time.sleep(min(tick, left))
        if n == 0 or (read_blend and bn == 0):
            # Sensor gone for a whole period: hold the current duty.
            continue
        temp = acc / n
        if read_blend:
            blend_temp = bacc / bn
            sensors = ((sensor_name, temp), (args.blend_zone_type, blend_temp))
            temp += args.blend_weight * blend_temp
        if args.duty is None:
            err = args.temp - temp
            integ = min(1.0, max(0.0, integ + args.ki * err * args.period))
            d = min(1.0, max(0.0, args.kp * err + integ))
            duty.value = d

        now = time.monotonic()
        if args.metrics and now - last_metrics >= args.metrics_interval:
            try:
                write_metrics(args.metrics, temp, args.temp, d, args.copies,
                              sensors, args.blend_weight)
            except OSError as e:
                print(f"ntpheat: metrics write failed: {e}", file=sys.stderr, flush=True)
            last_metrics = now

        for w in workers:
            if not w.is_alive():
                sys.exit("ntpheat: a burner died; exiting so systemd restarts us")


if __name__ == "__main__":
    main()
