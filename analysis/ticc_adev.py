# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "numpy",
#     "allantools",
#     "matplotlib",
# ]
# ///

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import allantools
    import matplotlib.pyplot as plt
    from pathlib import Path

    return Path, allantools, mo, np, plt


@app.cell
def _(mo):
    mo.md("""
    # TAPR TICC — ADEV & time-interval analysis

    Parses picocom logs from the TICC (`# `-prefixed header lines are
    skipped, anything that doesn't parse as a float is ignored). Readings
    are treated as **phase data** (time interval A→B, seconds) sampled at
    one reading per `tau0`.

    Select **multiple files** to compare captures side by side — every plot
    overlays the selected datasets. With nothing selected, all `.log` files
    in `data/` are loaded.

    The **samples** slider limits every dataset to that many readings from the
    start of the capture; at its far right it uses all available. Truncation
    happens before outlier removal, so the MAD filter sees only the selected
    window.
    """)
    return


@app.cell
def _(Path, mo):
    _data_dir = Path(__file__).parent / "data"
    file_browser = mo.ui.file_browser(
        initial_path=_data_dir if _data_dir.exists() else Path(__file__).parent,
        multiple=True,
        label="TICC log file(s)",
    )
    file_browser
    return (file_browser,)


@app.cell
def _(mo):
    tau0_input = mo.ui.number(
        value=1.0, start=0.001, stop=1000.0, label="τ₀ — seconds between readings"
    )
    tau_spacing = mo.ui.dropdown(
        options=["octave", "decade", "all"], value="octave", label="τ spacing"
    )
    remove_outliers = mo.ui.checkbox(value=True, label="Remove outliers (MAD filter)")
    outlier_k = mo.ui.number(value=5.0, start=1.0, stop=50.0, label="MAD threshold (σ-equivalent)")
    mo.hstack([tau0_input, tau_spacing, remove_outliers, outlier_k], justify="start", wrap=True)
    return outlier_k, remove_outliers, tau0_input, tau_spacing


@app.cell
def _(Path, file_browser, mo, np):
    def parse_ticc(path):
        """Return the numeric readings from a TICC/picocom log as a float array."""
        vals = []
        for line in Path(path).read_text(errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                vals.append(float(s.split()[0]))
            except ValueError:
                continue  # partial first/last lines, menu echoes, etc.
        return np.asarray(vals)

    if file_browser.value:
        selected_paths = [Path(_f.path) for _f in file_browser.value]
    else:
        _data_dir = Path(__file__).parent / "data"
        selected_paths = sorted(_data_dir.glob("*.log")) if _data_dir.exists() else []

    mo.stop(not selected_paths, mo.md("**Select one or more TICC log files above to begin.**"))

    raw_data = {}
    _skipped = []
    for _p in selected_paths:
        _vals = parse_ticc(_p)
        if _vals.size >= 8:
            raw_data[_p.name] = _vals
        else:
            _skipped.append(f"`{_p.name}` ({_vals.size} readings)")

    mo.stop(not raw_data, mo.md("**No usable data in the selected file(s).**"))
    mo.md(f"_Skipped (too few readings): {', '.join(_skipped)}_" if _skipped else "")
    return (raw_data,)


@app.cell
def _(mo, raw_data):
    _max_n = max(_v.size for _v in raw_data.values())
    sample_limit = mo.ui.slider(
        start=8,
        stop=_max_n,
        step=1,
        value=_max_n,
        label="Samples to use",
        show_value=True,
        include_input=True,
        full_width=True,
    )
    sample_limit
    return (sample_limit,)


@app.cell
def _(mo, raw_data, sample_limit):
    _max_n = max(_v.size for _v in raw_data.values())
    mo.md(
        f"_Using **all {_max_n:,}** available readings._"
        if sample_limit.value >= _max_n
        else f"_Using the first **{sample_limit.value:,}** of {_max_n:,} readings; "
        "a file with fewer contributes all of its own._"
    )
    return


@app.cell
def _(np, outlier_k, raw_data, remove_outliers, sample_limit):
    datasets = {}  # name -> (phase array, n_removed)
    for _name, _full in raw_data.items():
        # Truncate before the outlier filter so the MAD reflects the window
        # actually being analysed. Slicing past the end is a no-op, so short
        # files simply contribute everything they have.
        _raw = _full[: sample_limit.value]
        if remove_outliers.value:
            _med = np.median(_raw)
            _mad = np.median(np.abs(_raw - _med))
            if _mad > 0:
                _keep = np.abs(_raw - _med) <= outlier_k.value * 1.4826 * _mad
            else:
                _keep = np.ones(_raw.size, dtype=bool)
            datasets[_name] = (_raw[_keep], int(_raw.size - _keep.sum()))
        else:
            datasets[_name] = (_raw, 0)

    file_colors = {
        _name: f"C{_i % 10}" for _i, _name in enumerate(datasets)
    }
    return datasets, file_colors


@app.cell
def _(datasets, mo, np, tau0_input):
    _tau0 = tau0_input.value
    _rows = []
    for _name, (_phase, _n_removed) in datasets.items():
        _resid_ns = (_phase - _phase.mean()) * 1e9
        _rows.append(
            {
                "file": _name,
                "readings": f"{_phase.size} ({_n_removed} removed)",
                "duration": f"{_phase.size * _tau0:.0f} s",
                "mean interval": f"{_phase.mean():.11f} s",
                "std dev": f"{_resid_ns.std():.3f} ns",
                "peak-to-peak": f"{np.ptp(_resid_ns):.3f} ns",
            }
        )
    mo.ui.table(_rows, selection=None, label="Summary")
    return


@app.cell
def _(datasets, file_colors, np, plt, tau0_input):
    _tau0 = tau0_input.value
    _fig, _ax = plt.subplots(figsize=(9, 3.5))
    for _name, (_phase, _) in datasets.items():
        _t = np.arange(_phase.size) * _tau0
        _ax.plot(_t, (_phase - _phase.mean()) * 1e9, lw=0.7, color=file_colors[_name], label=_name)
    _ax.set_xlabel("Elapsed time (s)")
    _ax.set_ylabel("Phase − mean (ns)")
    _ax.set_title("Time interval readings (mean removed)")
    _ax.grid(True, alpha=0.3)
    _ax.legend()
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(datasets, file_colors, plt):
    _fig, _ax = plt.subplots(figsize=(9, 3.0))
    for _name, (_phase, _) in datasets.items():
        _resid_ns = (_phase - _phase.mean()) * 1e9
        _bins = min(80, max(10, _phase.size // 20))
        _ax.hist(_resid_ns, bins=_bins, alpha=0.55, color=file_colors[_name], label=_name)
    _ax.set_xlabel("Phase − mean (ns)")
    _ax.set_ylabel("Count")
    _ax.set_title("Distribution of readings")
    _ax.grid(True, alpha=0.3)
    _ax.legend()
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(datasets, file_colors, np, plt, tau0_input):
    _tau0 = tau0_input.value
    _fig, _ax = plt.subplots(figsize=(9, 3.0))
    for _name, (_phase, _) in datasets.items():
        _ffrac = np.diff(_phase) / _tau0
        _t = np.arange(_ffrac.size) * _tau0
        _ax.plot(_t, _ffrac * 1e9, lw=0.7, color=file_colors[_name], label=_name)
    _ax.set_xlabel("Elapsed time (s)")
    _ax.set_ylabel("Δphase/τ₀ (×10⁻⁹)")
    _ax.set_title("Fractional frequency (first difference of phase)")
    _ax.grid(True, alpha=0.3)
    _ax.legend()
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(mo):
    dev_select = mo.ui.multiselect(
        options=["ADEV", "OADEV", "MDEV", "HDEV"],
        value=["OADEV"],
        label="Deviations to plot",
    )
    dev_select
    return (dev_select,)


@app.cell
def _(allantools, datasets, dev_select, file_colors, mo, plt, tau0_input, tau_spacing):
    _funcs = {
        "ADEV": allantools.adev,
        "OADEV": allantools.oadev,
        "MDEV": allantools.mdev,
        "HDEV": allantools.hdev,
    }
    _markers = {"ADEV": "o", "OADEV": "o", "MDEV": "^", "HDEV": "v"}
    _styles = {"ADEV": "--", "OADEV": "-", "MDEV": "-.", "HDEV": ":"}
    _rate = 1.0 / tau0_input.value

    mo.stop(not dev_select.value, mo.md("**Pick at least one deviation type.**"))

    # (file, dev) -> (taus, devs, errs)
    dev_results = {}
    for _fname, (_phase, _) in datasets.items():
        for _dname in dev_select.value:
            _taus, _devs, _errs, _ns = _funcs[_dname](
                _phase, rate=_rate, data_type="phase", taus=tau_spacing.value
            )
            dev_results[(_fname, _dname)] = (_taus, _devs, _errs)

    _fig, _ax = plt.subplots(figsize=(9, 5))
    for (_fname, _dname), (_taus, _devs, _errs) in dev_results.items():
        _label = f"{_fname} — {_dname}" if len(dev_select.value) > 1 else _fname
        _ax.errorbar(
            _taus, _devs, yerr=_errs,
            marker=_markers[_dname], ms=4, capsize=3,
            linestyle=_styles[_dname], color=file_colors[_fname],
            label=_label,
        )
    _ax.set_xscale("log")
    _ax.set_yscale("log")
    _ax.set_xlabel("τ (s)")
    _ax.set_ylabel("σ(τ)")
    _title = " / ".join(dev_select.value)
    _ax.set_title(f"Frequency stability ({_title})")
    _ax.grid(True, which="both", alpha=0.3)
    _ax.legend()
    _fig.tight_layout()
    _fig
    return (dev_results,)


@app.cell
def _(allantools, datasets, file_colors, plt, tau0_input, tau_spacing):
    _fig, _ax = plt.subplots(figsize=(9, 4))
    for _name, (_phase, _) in datasets.items():
        _taus, _tdevs, _errs, _ns = allantools.tdev(
            _phase, rate=1.0 / tau0_input.value, data_type="phase", taus=tau_spacing.value
        )
        _ax.errorbar(
            _taus, _tdevs * 1e9, yerr=_errs * 1e9,
            marker="s", ms=4, capsize=3, color=file_colors[_name], label=_name,
        )
    _ax.set_xscale("log")
    _ax.set_yscale("log")
    _ax.set_xlabel("τ (s)")
    _ax.set_ylabel("TDEV (ns)")
    _ax.set_title("Time deviation")
    _ax.grid(True, which="both", alpha=0.3)
    _ax.legend()
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(dev_results, mo):
    _rows = []
    for (_fname, _dname), (_taus, _devs, _errs) in dev_results.items():
        for _t, _d, _e in zip(_taus, _devs, _errs):
            _rows.append(
                {
                    "file": _fname,
                    "deviation": _dname,
                    "tau_s": _t,
                    "sigma": f"{_d:.3e}",
                    "error": f"{_e:.3e}",
                }
            )
    mo.ui.table(_rows, selection=None, label="Deviation values", page_size=20)
    return


if __name__ == "__main__":
    app.run()
