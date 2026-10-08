# ntpheat

One role, two independent halves, each with its own task file, enable
flag and tag: `tasks/tmp117.yml` (the external TMP117 sensor,
`tmp117_enabled`) and `tasks/ntpheat.yml` (the heater, `ntpheat_enabled`).

## The heater (`tasks/ntpheat.yml`)

A SCHED_IDLE CPU heater that holds the GM's package temperature at a
setpoint, after the Raspberry Pi
[ntpheat](https://www.satsignal.eu/ntp/Raspberry-Pi-ntpheat.html). The aim
on the GM is stability of the ART (the crystal-derived Always Running
Timer behind the TSC and PCIe PTM); the package sensor is the nearest
proxy for that crystal's temperature.

`files/ntpheat.py` is a Python 3 rewrite: sensor chosen by thermal-zone
type (on the Mu, zone 0 is the 28 C ACPI board sensor and zone 1 is
`x86_pkg_temp`) or, with `--iio-name`, an IIO temperature device; a PI
controller on burn duty cycle; and `openssl speed` AES-256-GCM children as
the heat source, duty-cycled with SIGSTOP/SIGCONT. Duty, temperature and
setpoint go to node_exporter's textfile collector as `ntpheat_*`.

### Sensor: the TMP117 (since 2026-09-05)

The GM regulates on the external TI TMP117 that `tasks/tmp117.yml` enumerates
(`ntpheat_iio_name: tmp117`), not the package sensor. The package sensor is
the die hotspot: 1 C steps, +/-several C absolute, and ~10 C of ripple
within a burst, only usable after averaging. The TMP117 is +/-0.1 C with
7.8 mC steps, converts once a second, and sits where the oscillator is.
Consequences:

- **The setpoint is in TMP117 terms.** It reads roughly 20 C below the
  package at the same heat; the package-sensor budget below is a guide to
  the heater's authority, not to the number in `ntpheat_target_temp`.
- **It is slower, and the heater has less leverage over it.** Open-loop
  step test on the GM (2026-09-05, `--duty 1.0` from a cold heater, ~22 C
  room): the package jumped 52 -> 66 C, but the TMP117 rose only ~5 C per
  unit duty, first-order with a ~1000 s time constant and ~20 s dead time.
  Two consequences. The heater can hold the TMP117 against roughly +/-2 C
  of room change before the duty pins at 0 or 1 (it was +/-7 C in package
  terms), so the setpoint wants re-centring with the season. And the
  package-sensor gains (kp 0.02, ki 0.002) give a damping ratio of ~0.2 on
  this plant, a ~35 min hunt; the GM uses SIMC gains instead
  (`ntpheat_kp: 0.4`, `ntpheat_ki: 0.0004`, damping ~1, ~12 min
  closed-loop time constant). Re-measure with `--duty` if the sensor is
  moved.
- **Step tests:** stop the unit and run e.g.
  `chrt -i 0 nice -n 19 ntpheat.py --iio-name tmp117 --copies 4 --duty 1.0`
  while logging `tmp117.sh`; fit gain and time constant to the response,
  then `kp = tau / (K (tau/2 + theta))`, `ki = kp / tau`.
- The unit orders itself after `tmp117-i2c.service`, and the script waits
  up to 120 s at boot for the IIO device to appear.

### Heat budget on the GM (measured 2026-09-04)

The N100 is held at its **800 MHz base ratio**: `MSR_PLATFORM_INFO` says
max non-turbo ratio 8, and the BIOS has SpeedStep (EIST) and Turbo off,
so no cpufreq driver binds and every core reports ratio 8. Package power
over a 3.47 W idle with four burners, one per core:

| Burner | Extra power |
|---|---|
| OpenSSL AES-256-GCM (default) | +1.46 W |
| Python md5 loop (`--burner python`) | +0.95 W |
| OpenSSL SHA-256 | +0.74 W |
| AVX2 FMA loop | +0.55 W |

Thermal gain is ~5 C/W, so full output lifts the package from 52-54 C
idle to ~59-60 C. That ~6 C range is the whole control authority; the
setpoint in `group_vars/server.yml` sits mid-range. Watch
`ntpheat_duty_ratio`: pinned at 1.0 the room is too cold for the setpoint,
at 0.0 too warm.

### Getting more heat: a higher fixed frequency

Raising the 6 W power limit alone does nothing: at 800 MHz the package
peaks at 4.9 W, so PL1 never engages. Every ratio above 8 is a *turbo*
ratio (`MSR_TURBO_RATIO_LIMIT`: 34/34/31/29 for 1/2/3/4 active cores), so
a higher fixed frequency needs Turbo and EIST enabled in the BIOS and
then something to pin the ratio, since the hardware will not do it alone:

1. **BIOS**: enable Intel SpeedStep and Turbo Mode; leave Speed Shift
   (HWP) off so `IA32_PERF_CTL` writes are honoured; disable C1E (it drops
   idle cores to the minimum ratio). Raise PL1/PL2 (they are unlocked,
   currently 6 W) above what four cores draw at the chosen ratio, or RAPL
   will modulate the frequency exactly the way the lock was meant to
   prevent.
2. **Kernel**: keep every cpufreq governor out (`intel_pstate=disable` on
   the command line, blacklist `acpi_cpufreq`), otherwise the OS starts
   scaling again.
3. **Pin the ratio once at boot**, e.g. 1.6 GHz on all cores:

       wrmsr -a 0x199 0x1000        # ratio 0x10 = 16 -> 1.6 GHz

   (`msr-tools`; lockdown is off on the Mu so `/dev/cpu/*/msr` is
   writable). Confirm with `rdmsr -a -f 15:8 0x198`. Core power scales
   roughly with frequency times voltage squared, so 1.6 GHz should give
   the heater several watts of range instead of 1.5. Measure with
   `/sys/class/powercap/intel-rapl:0/energy_uj` before choosing the
   setpoint; idle temperature rises too at the higher ratio.

**Done on the GM, 2026-09-04, as host-only config (not in this repo):**
BIOS SpeedStep and Turbo on, PL1/PL2 12 W; `/etc/default/grub.d/98-cpu-pin.cfg`
adds `cpufreq.off=1` (acpi-cpufreq is built in, so the kernel side has to be
the cpufreq core switch, not a blacklist) and `/etc/grub.d/06_cpu_pin` has
GRUB itself run `wrmsr 0x199 0x1000` at boot. GRUB only writes the boot
CPU, but the N100's single frequency domain follows the highest request
(verified: cpu0 at 16, others at 8 gives 1600 MHz on all cores). Result:
idle 3.8 W / 55-56 C, four AES burners 7.3 W, so ~3.5 W of heater
headroom instead of 1.5 W; setpoint raised to 62 C. If the GRUB write
fails the CPU stays at the BIOS boot ratio (800 MHz), never turbo.

Alternatively the BIOS "Boot performance mode: Turbo Performance" pins
the boot ratio at the top turbo bin without any MSR write, but that is
2.9 GHz on four active cores and will need a much higher PL and a check
on cooling.

## The TMP117 sensor (`tasks/tmp117.yml`)

TI TMP117 (+/-0.1 C) I2C temperature sensor on one of the Mu's host I2C
buses, the sensor `ntpheat` regulates on. The Mu's firmware has no node for it, so the kernel's
`tmp117` IIO driver has to be told where it is: `tmp117-i2c.service` writes
`tmp117 <addr>` to the bus's `new_device` file at boot, after which the
sensor appears as `/sys/bus/iio/devices/iio:deviceN` (name `tmp117`,
`in_temp_raw` x `in_temp_scale` mC).

Bus and address live in `defaults/main.yml` (`tmp117_i2c_bus`,
`tmp117_i2c_addr`); the GM has it on `i2c-3` at `0x48`. Gated on
`tmp117_enabled` (tag `tmp117`), independently of the heater.

Readout:

    tmp117.sh        # one reading, degrees C
    tmp117.sh 1      # timestamped line every second

Bench checks (`i2c-tools` is installed by the task file): `i2cdetect -y -r 3` shows
`UU` at 48 once the driver is bound (`-r`: the DesignWare adapter has no
SMBus Quick Write, so the default probe skips the 0x40 row); unbind first (`echo 0x48 >
/sys/bus/i2c/devices/i2c-3/delete_device`) to talk to it raw, e.g.
`i2cget -y 3 0x48 0x0f w` should give `0x1701` (device ID 0x0117,
byte-swapped).
