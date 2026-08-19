# TICC time analysis (marimo)

Marimo notebook for analyzing TAPR TICC time-interval captures: phase/frequency
plots, histograms, ADEV / OADEV / MDEV / HDEV, and TDEV (via
[allantools](https://github.com/aewallin/allantools)).

## Capturing data

On the measurement box, log the TICC serial output with picocom:

```bash
sudo picocom -b 115200 --logfile ticc.log /dev/ttyACM0
```

Copy the resulting log into `analysis/data/`. The parser skips the `#` header
lines and any partial/garbage lines, so raw picocom logs work as-is.

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
