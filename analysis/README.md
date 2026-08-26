# TICC time analysis (marimo)

Marimo notebook for analyzing TAPR TICC time-interval captures: phase/frequency
plots, histograms, ADEV / OADEV / MDEV / HDEV, and TDEV (via
[allantools](https://github.com/aewallin/allantools)).

## Capturing data

On the GM (`timeserver`, 10.3.30.123), log the TICC serial output with picocom
into `~/TICC/`:

```bash
sudo picocom -b 115200 --logfile ~/TICC/<name>.log /dev/ttyACM0
```

Logs sync into `analysis/data/raw/` automatically via mutagen (session defined
in `mutagen.yml` at the repo root):

```bash
mutagen project start      # begin continuous sync (run from repo root)
mutagen sync list          # status / conflicts
mutagen project terminate  # stop
```

The sync is one-way-safe (GM → local): local edits under `data/raw/` are never
overwritten and show up as conflicts instead. Curated/trimmed segments are
still promoted from `data/raw/` to `data/` by hand. The parser skips the `#`
header lines and any partial/garbage lines, so raw picocom logs work as-is.

## Running

Requires only [uv](https://docs.astral.sh/uv/) — dependencies are declared
inline in the notebook (PEP 723) and installed into a sandbox automatically:

```bash
uvx marimo edit --sandbox analysis/ticc_adev.py
```

## Notes

- Readings are treated as **phase data** (time interval A→B in seconds).
  With 1 PPS on both channels, τ₀ = 1 s (the default; adjustable in the UI).
- The constant offset (e.g. readings near −2 s from timestamp wrap) doesn't
  matter — ADEV and friends are invariant to it, and plots remove the mean.
- An optional MAD-based outlier filter (on by default, 5σ) drops PPS glitches
  before computing deviations.
- `data/sample-ticc.log` is a short real capture for smoke-testing the
  notebook; drop your own logs alongside it.
- `data/TC-ART-ac.log` and `data/TC-ART-ac2.log` are the two halves of a single
  capture of the Timecard PPS (chA) against the Mu's TGPIO 1PPS on pin 123
  (chB), split at interval sample 9988. **Both halves are AC-steered**
  (chrony refclock `PHC /dev/ptp2:nocrossts`, software reads). The second
  half was originally named `TC-ART-ptm.log` on the belief that the split
  marked an AC→PTM refclock switch; it doesn't — the capture (created 16:03,
  16325 samples at 1 Hz, so ended ~20:35 on 2026-08-24) finished before
  chronyd first ran with the PTM refclock selected (~22:01). Details in the
  header blocks. The halves still make a useful afternoon-vs-evening wander
  comparison (sd 13.95 vs 16.78 ns; the excess is low-frequency — the
  per-second white noise of the halves matches at ~8.4 vs 8.5 ns). The
  original is
  preserved at `data/raw/TC-ART-default.log`, deliberately outside the
  `*.log` glob so the "nothing selected" default doesn't load those samples
  twice. To compare the halves fairly, set the samples slider to 6337 so both
  use equal-length windows.
- `data/TC-ART-dpoll-5.log` is the first capture with PTM cross-timestamps
  actually steering the clock (`refclock PHC /dev/ptp2 poll 0 dpoll -5`,
  32 crosstimestamps/s median-filtered): mean 45.0 ns, sd 12.0 ns. The
  ~376 ns mean shift vs the AC captures is the static EXTENDED-vs-PRECISE
  readout bias (the gettimex latch instant sits ~0.4 µs past the midpoint
  of its ~3.2 µs read window, and chrony assumes the midpoint); the
  independent NIC/ts2phc chain sides with PRECISE. The dpoll averaging also
  cut servo-band wander (TDEV @ 32 s ~4.9 ns vs ~6.2–7.2 ns at 1 Hz). The
  curated file keeps the first 1670 s; the full capture — which ran on to
  ~13:33 and recorded the 13:27:53 PTM-requester wedge as a transient/drift
  tail — is archived at `data/raw/TC-ART-dpoll-5-full.log`.
