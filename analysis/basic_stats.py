# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "numpy",
#     "matplotlib",
# ]
# ///

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import matplotlib.pyplot as plt
    from pathlib import Path
    from ticc_log import parse_ticc

    return Path, mo, np, parse_ticc, plt


@app.cell
def _(mo):
    mo.md(r"""
    # Basic statistics on a PPS capture

    A learning notebook. It takes the ideas from the notepad — sample mean vs
    population mean, the data vector split into a *residual* part and a
    *mean* part, and where the degrees of freedom go — and applies them to
    one TICC capture of the Timecard PPS against the Mu's PPS.

    Each reading $x_i$ is a time interval A→B in seconds (Timestamp-mode
    captures are paired into chB − chA by `ticc_log.py`). We convert to ns.

    | Symbol | Meaning here |
    |---|---|
    | $x_i$ | one 1 PPS interval reading, in ns |
    | $n$ | how many readings we look at |
    | $\bar{x} = \frac{1}{n}\sum x_i$ | **sample mean**: the static offset we *estimate* from a window |
    | $\mu$ | **population mean**: the "true" offset of the clock pair. We never see it; $N$ is infinite because the clocks keep ticking |
    """)
    return


@app.cell
def _(Path, mo):
    _data_dir = Path(__file__).parent / "data"
    _default = _data_dir / "test-F9T_20260903-175907.log"
    file_browser = mo.ui.file_browser(
        initial_path=_data_dir if _data_dir.exists() else Path(__file__).parent,
        multiple=False,
        label="TICC log file",
    )
    mo.vstack([file_browser, mo.md(f"With nothing selected: `{_default.name}`")])
    return (file_browser,)


@app.cell
def _(Path, file_browser, mo, np, parse_ticc):
    if file_browser.value:
        _path = Path(file_browser.value[0].path)
    else:
        _path = Path(__file__).parent / "data" / "test-F9T_20260903-175907.log"

    _log = parse_ticc(_path.read_bytes())
    _raw = _log.phase * 1e9  # seconds -> ns
    mo.stop(_raw.size < 8, mo.md(f"**`{_path.name}` has only {_raw.size} readings.**"))

    # Drop PPS glitches with a MAD filter so a handful of outliers don't
    # dominate every mean and variance below. Same idea as in ticc_adev.py.
    _med = np.median(_raw)
    _mad = np.median(np.abs(_raw - _med)) * 1.4826
    _keep = np.abs(_raw - _med) < 5 * _mad
    x = _raw[_keep]
    n_total = x.size

    mo.md(
        f"Loaded **`{_path.name}`** ({_log.describe()}): "
        f"{(~_keep).sum()} dropped as outliers (>5 MAD), **n = {n_total}** kept."
    )
    return n_total, x


@app.cell
def _(mo):
    mo.md(r"""
    ## 1. Sample mean vs population mean

    The notepad says: *as $n$ grows it approaches $N$ and therefore
    $\bar{x} \to \mu$*. For a clock there is no finite $N$, so the honest
    version is: **as $n$ grows, $\bar{x}$ settles towards $\mu$**, and we can
    watch that happen by computing the running mean $\bar{x}_n$ of the first
    $n$ readings for every $n$.

    We use the mean of the *whole* capture as our stand-in for $\mu$. It is
    still a sample mean, just the biggest one we have.
    """)
    return


@app.cell
def _(mo, n_total, np, plt, x):
    mu_hat = x.mean()
    _running = np.cumsum(x) / np.arange(1, n_total + 1)

    _fig, _ax = plt.subplots(figsize=(9, 4))
    _ax.plot(np.arange(1, n_total + 1), _running, lw=1, label=r"running mean $\bar{x}_n$")
    _ax.axhline(mu_hat, color="k", ls="--", lw=1, label=rf"whole-capture mean = {mu_hat:.2f} ns")
    _ax.set_xscale("log")
    _ax.set_xlabel("n (readings used)")
    _ax.set_ylabel("ns")
    _ax.set_title("Sample mean settling as n grows")
    _ax.grid(True, which="both", alpha=0.3)
    _ax.legend()
    _fig.tight_layout()

    _rows = [
        {"n": _n, "x̄_n (ns)": f"{_running[_n - 1]:.2f}", "x̄_n − μ̂ (ns)": f"{_running[_n - 1] - mu_hat:+.2f}"}
        for _n in (1, 2, 5, 10, 100, 1000, 10000, n_total) if _n <= n_total
    ]
    mo.vstack([_fig, mo.ui.table(_rows, selection=None)])
    return (mu_hat,)


@app.cell
def _(mo):
    mo.md(r"""
    ## 2. The data vector split in two

    Take the first $n$ readings as one vector $X \in \mathbb{R}^n$. The notepad
    writes each component as $x_i = (x_i - \bar{x}) + \bar{x}$, so

    $$
    X \;=\; \underbrace{(X - \bar{x}\,\mathbf{1})}_{\text{residual}}
        \;+\; \underbrace{\bar{x}\,\mathbf{1}}_{\text{mean part}},
    \qquad \mathbf{1} = (1, 1, \dots, 1).
    $$

    The bottom-right of the notepad proves $\sum (x_i - \bar{x}) = 0$. In
    vector language that is the dot product $(X - \bar{x}\mathbf{1}) \cdot \mathbf{1} = 0$:
    **the residual is perpendicular to the mean direction**, exactly the
    right-angle in the sketch. Two consequences:

    * Pythagoras: $\|X\|^2 = \|X - \bar{x}\mathbf{1}\|^2 + n\,\bar{x}^2$.
    * The residual is stuck in the $(n-1)$-dimensional plane perpendicular
      to $\mathbf{1}$. That is the "$n-1$ d.o.f." Its one lost dimension went
      to $\bar{x}$.

    Pick $n$ below. With $n=2$ the axes are $x_1, x_2$ and the picture is the
    notepad sketch. For larger $n$ we can't draw $\mathbb{R}^n$, so the plot
    slices through the one plane that contains all three vectors: the mean
    direction $\mathbf{1}$ horizontally, the residual direction vertically.
    The triangle is always a right triangle; only the leg lengths change.
    """)
    return


@app.cell
def _(mo, n_total):
    n_vec = mo.ui.slider(start=2, stop=10, value=2, label="n for the vector picture")
    start_vec = mo.ui.slider(
        start=0, stop=n_total - 10, step=10, value=n_total // 2,
        label="first reading to use (the capture start is still settling)",
    )
    center_vec = mo.ui.checkbox(
        value=True, label="subtract the whole-capture mean μ̂ first (so both legs are a few ns and visible)"
    )
    mo.vstack([mo.hstack([n_vec, start_vec], justify="start", wrap=True), center_vec])
    return center_vec, n_vec, start_vec


@app.cell
def _(center_vec, mo, mu_hat, n_vec, np, plt, start_vec, x):
    _n = n_vec.value
    _i0 = start_vec.value
    # Shifting every reading by a constant doesn't change the residual and
    # shifts x̄ by the same constant, so the geometry is the same. Without the
    # shift the ~50 ns offset dwarfs the ~3 ns residual and the triangle is a
    # sliver.
    _X = x[_i0:_i0 + _n] - (mu_hat if center_vec.value else 0.0)
    _xbar = _X.mean()
    _ones = np.ones(_n)
    _mean_part = _xbar * _ones
    _resid = _X - _mean_part

    _dot = float(_resid @ _ones)
    _lhs = float(_X @ _X)
    _rhs = float(_resid @ _resid + _n * _xbar**2)

    _md = mo.md(
        f"""
        readings {_i0}…{_i0 + _n - 1}: n = {_n}, x̄ = {_xbar:.3f} ns{" (relative to μ̂)" if center_vec.value else ""}

        | check | value |
        |---|---|
        | residual · **1** = Σ(xᵢ − x̄) | {_dot:.3e} ns (zero up to float rounding) |
        | ‖X‖² | {_lhs:.3f} |
        | ‖residual‖² + n·x̄² | {_rhs:.3f} |
        | ‖residual‖² alone | {float(_resid @ _resid):.3f}  ← this is what variance is built from |
        """
    )

    _fig, _ax = plt.subplots(figsize=(5.5, 5.5))
    if _n == 2:
        # Raw axes: x1 horizontal, x2 vertical. The mean direction is the diagonal.
        _px, _py = _X
        _mx, _my = _mean_part
        _rx, _ry = _resid
        _xlabel, _ylabel = "x₁ (ns)", "x₂ (ns)"
        _diag = "mean direction (1,1)"
        _title = "Data vector = mean part + residual (n = 2)"
    else:
        # For n ≥ 3 we can't draw R^n, but X, x̄·1 and the residual all lie in
        # one plane: the one spanned by 1 and the residual. Use unit vectors
        # along each as the two axes. Coordinates: along 1̂ it's √n·x̄,
        # along r̂ it's ‖residual‖. Same right triangle, any n.
        _px, _py = np.sqrt(_n) * _xbar, float(np.linalg.norm(_resid))
        _mx, _my = _px, 0.0
        _rx, _ry = 0.0, _py
        _xlabel = r"along $\hat{\mathbf{1}}$ — the mean direction (ns)"
        _ylabel = r"along $\hat{r}$ — one direction in the $(n-1)$-dim residual plane (ns)"
        _diag = None
        _title = f"Same picture, sliced through the plane of $\\mathbf{{1}}$ and the residual (n = {_n})"

    _ax.quiver(0, 0, _px, _py, angles="xy", scale_units="xy", scale=1, color="k", label="X")
    _ax.quiver(0, 0, _mx, _my, angles="xy", scale_units="xy", scale=1, color="tab:blue", label=r"$\bar{x}\,\mathbf{1}$")
    _ax.quiver(_mx, _my, _rx, _ry, angles="xy", scale_units="xy", scale=1, color="tab:red", label=r"$X-\bar{x}\,\mathbf{1}$")
    _lim = max(abs(_px), abs(_py)) * 1.3
    if _diag:
        _ax.plot([-_lim, _lim], [-_lim, _lim], color="tab:blue", lw=0.5, ls=":", label=_diag)
    _ax.set_xlim(-_lim, _lim)
    _ax.set_ylim(-_lim, _lim)
    _ax.set_aspect("equal")
    _ax.axhline(0, color="gray", lw=0.5)
    _ax.axvline(0, color="gray", lw=0.5)
    _ax.set_xlabel(_xlabel)
    _ax.set_ylabel(_ylabel)
    _ax.set_title(_title, fontsize=10)
    _ax.legend(loc="lower right", fontsize=8)
    _fig.tight_layout()
    mo.hstack([_fig, _md], widths=[1, 1])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 3. Why variance divides by $n-1$

    Squared length of the residual, spread over its degrees of freedom:

    $$
    s^2 = \frac{\|X - \bar{x}\mathbf{1}\|^2}{n-1} = \frac{\sum (x_i-\bar{x})^2}{n-1}.
    $$

    Dividing by $n$ instead is biased low, because $\bar{x}$ was chosen from
    the same data and always sits "in the middle" of it. The bias is exactly
    one dimension's worth of squared length, on average.

    We can *see* the bias. Draw many random $n$-reading subsamples from the
    capture, compute both versions, and compare their average to the variance
    of the whole capture (our stand-in for the population variance $\sigma^2$).
    """)
    return


@app.cell
def _(mo):
    n_sub = mo.ui.slider(start=2, stop=30, value=5, label="subsample size n")
    n_sub
    return (n_sub,)


@app.cell
def _(mo, n_sub, n_total, np, x):
    _n = n_sub.value
    _K = 4000
    _rng = np.random.default_rng(0)
    _sigma2 = x.var(ddof=1)  # whole-capture, our best σ² stand-in

    # (a) scattered picks: readings spread across the capture, close to independent
    _idx = _rng.integers(0, n_total, size=(_K, _n))
    _sub = x[_idx]
    _v_n = _sub.var(axis=1, ddof=0).mean()
    _v_n1 = _sub.var(axis=1, ddof=1).mean()

    # (b) contiguous windows: n consecutive seconds, as you'd naturally take them
    _starts = _rng.integers(0, n_total - _n, size=_K)
    _win = np.stack([x[_s:_s + _n] for _s in _starts])
    _w_n = _win.var(axis=1, ddof=0).mean()
    _w_n1 = _win.var(axis=1, ddof=1).mean()

    mo.md(
        f"""
        n = {_n}, {_K} subsamples each. Whole-capture variance σ̂² = **{_sigma2:.1f} ns²** (sd {np.sqrt(_sigma2):.2f} ns).

        | estimator | scattered picks | contiguous windows |
        |---|---|---|
        | divide by n   | {_v_n:.1f} ns² ({_v_n / _sigma2:.2f}·σ̂²) | {_w_n:.1f} ns² ({_w_n / _sigma2:.2f}·σ̂²) |
        | divide by n−1 | {_v_n1:.1f} ns² ({_v_n1 / _sigma2:.2f}·σ̂²) | {_w_n1:.1f} ns² ({_w_n1 / _sigma2:.2f}·σ̂²) |
        | theory for iid, ÷n | ratio (n−1)/n = {(_n - 1) / _n:.2f} | |

        **Scattered picks** behave like the textbook: ÷n lands near (n−1)/n of
        σ̂², ÷(n−1) lands near 1.

        **Contiguous windows** are lower even with n−1. Neighbouring seconds
        are not independent: the offset wanders slowly, so a short window only
        sees the fast part of the noise. That is the limit of "basic
        statistics" for clocks, and the reason the other notebook uses ADEV
        and TDEV, which measure spread *as a function of window length*
        instead of pretending one σ describes everything.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 4. How well do we know the offset? Standard error

    If the readings were independent, the sample mean of $n$ of them has
    standard deviation $s/\sqrt{n}$, the **standard error**. It says how far
    $\bar{x}$ typically sits from $\mu$. Below, the theoretical $s/\sqrt{n}$
    is compared to what actually happens when you take contiguous windows of
    $n$ seconds and look at how much their means scatter.
    """)
    return


@app.cell
def _(mo, mu_hat, n_total, np, x):
    _s = x.std(ddof=1)
    _rows = []
    for _n in (1, 10, 100, 1000, 10000):
        if _n > n_total // 4:
            break
        _m = n_total // _n
        _block_means = x[: _m * _n].reshape(_m, _n).mean(axis=1)
        _rows.append(
            {
                "window n (s)": _n,
                "s/√n, iid theory (ns)": f"{_s / np.sqrt(_n):.2f}",
                "observed sd of window means (ns)": f"{_block_means.std(ddof=1):.2f}",
                "windows": _m,
            }
        )
    mo.vstack(
        [
            mo.md(f"Whole capture: x̄ = **{mu_hat:.2f} ns**, s = **{_s:.2f} ns**, n = {n_total}."),
            mo.ui.table(_rows, selection=None),
            mo.md(
                "Where the observed column stops shrinking like $1/\\sqrt{n}$, "
                "averaging longer has stopped buying accuracy: the slow wander of "
                "the offset, not the per-second jitter, is what limits $\\bar{x}$."
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 5. The same numbers as pictures

    Left: histogram of all readings with $\bar{x}$ and $\bar{x} \pm s$.
    Right: mean of every 60 s block over the capture. If $\mu$ were a fixed
    number and the noise white, the right-hand plot would be flat noise of
    size $s/\sqrt{60}$; the structure you see is the wander.
    """)
    return


@app.cell
def _(mu_hat, n_total, np, plt, x):
    _s = x.std(ddof=1)
    _fig, (_a1, _a2) = plt.subplots(1, 2, figsize=(11, 4))

    _a1.hist(x, bins=80, color="tab:gray", alpha=0.8)
    _a1.axvline(mu_hat, color="tab:blue", lw=2, label=rf"$\bar{{x}}$ = {mu_hat:.2f} ns")
    _a1.axvline(mu_hat - _s, color="tab:red", ls="--", label=rf"$\bar{{x}} \pm s$, s = {_s:.2f} ns")
    _a1.axvline(mu_hat + _s, color="tab:red", ls="--")
    _a1.axvline(np.median(x), color="tab:green", ls=":", label=f"median = {np.median(x):.2f} ns")
    _a1.set_xlabel("interval A→B (ns)")
    _a1.set_ylabel("count")
    _a1.set_title("All readings")
    _a1.legend(fontsize=8)

    _b = 60
    _m = n_total // _b
    _bm = x[: _m * _b].reshape(_m, _b).mean(axis=1)
    _t = np.arange(_m) * _b / 60.0
    _a2.plot(_t, _bm, lw=1)
    _a2.axhline(mu_hat, color="k", ls="--", lw=1)
    _a2.fill_between(_t, mu_hat - _s / np.sqrt(_b), mu_hat + _s / np.sqrt(_b), color="tab:blue", alpha=0.2, label=r"$\bar{x} \pm s/\sqrt{60}$ (iid expectation)")
    _a2.set_xlabel("minutes into capture")
    _a2.set_ylabel("60 s block mean (ns)")
    _a2.set_title("Does the mean stay put?")
    _a2.legend(fontsize=8)
    for _a in (_a1, _a2):
        _a.grid(True, alpha=0.3)
    _fig.tight_layout()
    _fig
    return


if __name__ == "__main__":
    app.run()
