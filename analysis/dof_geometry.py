# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "numpy",
#     "plotly==7.0.0",
# ]
# ///

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import numpy as np
    import plotly.graph_objects as go

    return go, mo, np


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Where the *n − 1* comes from — the geometry of a sample

    A sample of $n$ readings is **one point** $X = (x_1, \dots, x_n)$ in
    $\mathbb{R}^n$. Every statistic we compute is some geometry done on that
    point. Two decompositions of the same vector are drawn below, exactly as
    on the whiteboard:

    $$
    X \;=\; \underbrace{(X - \mu\mathbf{1})}_{\color{#2a78d6}{\text{error vector}},\; n \text{ DoF}}
        \;+\; \underbrace{\mu\mathbf{1}}_{\color{#008300}{\text{expected-value vector}},\; 0 \text{ DoF}}
    $$

    $$
    X \;=\; \underbrace{(X - \bar{x}\mathbf{1})}_{\color{#e34948}{\text{residual vector}},\; n-1 \text{ DoF}}
        \;+\; \underbrace{\bar{x}\mathbf{1}}_{\text{sample-mean vector},\; 1 \text{ DoF}}
    $$

    where $\mathbf{1} = (1, \dots, 1)$. The three arrows the whiteboard asks
    about are the sides of one right triangle:

    * $\color{#2a78d6}{X - \mu\mathbf{1}}$ — what we *wish* we could measure
      (needs the true $\mu$).
    * $\color{#e34948}{X - \bar{x}\mathbf{1}}$ — what we *can* measure.
    * $\color{#eda100}{(\bar{x} - \mu)\mathbf{1}}$ — the piece the sample mean
      swallowed. It always points along $\mathbf{1}$.

    Drag the sliders. The right angle at $\bar{x}\mathbf{1}$ never goes away:
    $\bar{x}\mathbf{1}$ is the **orthogonal projection** of $X$ onto the line
    spanned by $\mathbf{1}$, so the residual is always perpendicular to it.
    That perpendicularity is the whole story of degrees of freedom.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    x1 = mo.ui.slider(-4, 4, 0.1, value=0.6, label="x₁", show_value=True)
    x2 = mo.ui.slider(-4, 4, 0.1, value=2.6, label="x₂", show_value=True)
    x3 = mo.ui.slider(-4, 4, 0.1, value=1.4, label="x₃ (3-D only)", show_value=True)
    mu = mo.ui.slider(-3, 3, 0.1, value=1.0, label="μ  (true mean)", show_value=True)
    sigma = mo.ui.slider(0.1, 2.0, 0.1, value=0.8, label="σ  (true sd)", show_value=True)
    show_cloud = mo.ui.checkbox(value=False, label="overlay random samples X ~ N(μ, σ²)")
    n_cloud = mo.ui.slider(20, 600, 10, value=200, label="samples", show_value=True)
    seed = mo.ui.number(0, 9999, value=1, label="seed")
    mo.vstack(
        [
            mo.hstack([x1, x2, x3], justify="start", gap=2),
            mo.hstack([mu, sigma], justify="start", gap=2),
            mo.hstack([show_cloud, n_cloud, seed], justify="start", gap=2),
        ]
    )
    return mu, n_cloud, seed, show_cloud, sigma, x1, x2, x3


@app.cell(hide_code=True)
def _(np):
    # Palette (validated light-mode categorical slots; every arrow is also
    # direct-labelled so colour is never the only cue).
    C = {
        "err": "#2a78d6",  # blue   — error vector X − μ1
        "res": "#e34948",  # red    — residual vector X − x̄1
        "mu": "#008300",  # green  — expected-value vector μ1
        "shift": "#eda100",  # yellow — (x̄ − μ)1, the piece along 1
        "mean": "#0b0b0b",  # ink    — sample-mean vector x̄1 and X itself
        "guide": "#b5b3ad",  # grey   — construction lines
        "ink": "#0b0b0b",
    }

    def decompose(x, mu):
        """Split a sample vector x both ways (whiteboard, bottom half)."""
        x = np.asarray(x, dtype=float)
        n = x.size
        one = np.ones(n)
        xbar = x.mean()
        return {
            "n": n,
            "x": x,
            "one": one,
            "xbar": xbar,
            "mu": mu,
            "mu_vec": mu * one,  # expected-value vector    (0 DoF)
            "mean_vec": xbar * one,  # sample-mean vector       (1 DoF)
            "err": x - mu * one,  # error vector             (n DoF)
            "resid": x - xbar * one,  # residual vector          (n−1 DoF)
            "shift": (xbar - mu) * one,  # what the mean swallowed  (along 1)
        }

    def right_angle(d, size):
        """Three corner points of the little square drawn at x̄1."""
        c = d["mean_vec"]
        u = d["one"] / np.sqrt(d["n"])
        # Point the square's first leg back toward μ1 (or +1 if x̄ == μ).
        u = u * (np.sign(d["mu"] - d["xbar"]) or 1.0)
        r = np.linalg.norm(d["resid"])
        v = d["resid"] / r if r > 1e-12 else np.zeros_like(c)
        return np.array([c + size * u, c + size * u + size * v, c + size * v])

    def outward(d, pos, dist):
        """pos nudged by `dist` away from the triangle's centroid (label placement)."""
        centroid = (d["x"] + d["mu_vec"] + d["mean_vec"]) / 3
        v = np.asarray(pos, float) - centroid
        nv = np.linalg.norm(v)
        return pos if nv < 1e-9 else pos + dist * v / nv

    def face_on_camera(d, tilt=0.25):
        """Camera eye along the normal of the plane spanned by 1 and the residual,
        so the right triangle is seen face-on (3-D only)."""
        nrm = np.cross(d["one"], d["resid"])
        if np.linalg.norm(nrm) < 1e-9:
            return dict(x=1.45, y=-1.55, z=0.75)
        nrm /= np.linalg.norm(nrm)
        if nrm @ np.array([1.0, -1.0, 0.6]) < 0:
            nrm = -nrm
        eye = 1.9 * nrm + tilt * d["one"] / np.sqrt(d["n"])
        return dict(x=float(eye[0]), y=float(eye[1]), z=float(eye[2]))

    def cloud(d, sigma, k, seed):
        """k random samples; residuals re-anchored at μ1 so they share a tail."""
        rng = np.random.default_rng(int(seed))
        xs = rng.normal(d["mu"], sigma, size=(k, d["n"]))
        resid = xs - xs.mean(axis=1, keepdims=True)
        return xs, d["mu_vec"] + resid

    return C, cloud, decompose, face_on_camera, outward, right_angle


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## n = 2 — the whiteboard picture, live

    Both axes are readings. The dashed diagonal is the line spanned by
    $\mathbf{1}$ — every "constant vector" ($\mu\mathbf{1}$, $\bar{x}\mathbf{1}$)
    lives on it. The dotted line through $\bar{x}\mathbf{1}$ is everything
    perpendicular to it — for $n=2$ that is a single direction, so the
    residual has exactly **one** number of freedom in it, not two.

    Tick *overlay random samples* to see the point of it: blue dots are
    fresh samples $X$ (they scatter in **both** directions around
    $\mu\mathbf{1}$); red dots are their residual vectors with tails slid to
    $\mu\mathbf{1}$ — they all collapse onto one line: the perpendicular to
    $\mathbf{1}$ through $\mu\mathbf{1}$ (parallel to the dotted guide).
    """)
    return


@app.cell(hide_code=True)
def _(
    C,
    cloud,
    decompose,
    go,
    mu,
    n_cloud,
    right_angle,
    seed,
    show_cloud,
    sigma,
    x1,
    x2,
):
    d2 = decompose([x1.value, x2.value], mu.value)

    def _arrow(tail, tip, color, width=3):
        return go.layout.Annotation(
            x=tip[0], y=tip[1], ax=tail[0], ay=tail[1],
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowsize=1.1, arrowwidth=width,
            arrowcolor=color, text="",
        )

    def _label(pos, text, color, xshift=0, yshift=0):
        return go.layout.Annotation(
            x=pos[0], y=pos[1], xref="x", yref="y", text=text, showarrow=False,
            font=dict(size=14, color=C["ink"]), bgcolor="rgba(252,252,251,0.9)",
            bordercolor=color, borderwidth=1.5, borderpad=3,
            xshift=xshift, yshift=yshift,
        )

    _pts = [d2["x"], d2["mu_vec"], d2["mean_vec"], [0, 0]]
    _cl = None
    if show_cloud.value:
        _cl = cloud(d2, sigma.value, n_cloud.value, seed.value)
        _pts += [_cl[0].min(0), _cl[0].max(0), _cl[1].min(0), _cl[1].max(0)]
    import numpy as _np

    _all = _np.array(_pts, dtype=float)
    _lo, _hi = _all.min() - 0.7, _all.max() + 0.7
    _L = 2 * max(abs(_lo), abs(_hi))

    _traces = []
    # Guide: the line spanned by 1 (the "mean direction").
    _traces.append(go.Scatter(x=[-_L, _L], y=[-_L, _L], mode="lines",
                              line=dict(color=C["guide"], width=1.5, dash="dash"),
                              hoverinfo="skip", name="line spanned by 𝟏", showlegend=True))
    # Guide: the perpendicular through x̄1 (direction (1,−1)).
    _c = d2["mean_vec"]
    _traces.append(go.Scatter(x=[_c[0] - _L, _c[0] + _L], y=[_c[1] + _L, _c[1] - _L], mode="lines",
                              line=dict(color=C["res"], width=1, dash="dot"),
                              hoverinfo="skip", name="⊥ to 𝟏 through x̄𝟏 (1 DoF)", showlegend=True))
    if _cl is not None:
        _traces.append(go.Scatter(x=_cl[0][:, 0], y=_cl[0][:, 1], mode="markers",
                                  marker=dict(size=7, color=C["err"], opacity=0.45,
                                              line=dict(width=1, color="#fcfcfb")),
                                  name="samples X (fill the plane)",
                                  hovertemplate="X = (%{x:.2f}, %{y:.2f})<extra></extra>"))
        _traces.append(go.Scatter(x=_cl[1][:, 0], y=_cl[1][:, 1], mode="markers",
                                  marker=dict(size=7, color=C["res"], opacity=0.55,
                                              line=dict(width=1, color="#fcfcfb")),
                                  name="residuals, tails at μ𝟏 (one line)",
                                  hovertemplate="μ𝟏 + resid = (%{x:.2f}, %{y:.2f})<extra></extra>"))
    # Right-angle square.
    _sq = right_angle(d2, 0.12 * (_hi - _lo))
    _traces.append(go.Scatter(x=_sq[:, 0], y=_sq[:, 1], mode="lines",
                              line=dict(color=C["ink"], width=1.5), hoverinfo="skip", showlegend=False))
    # Key points.
    _traces.append(go.Scatter(
        x=[d2["x"][0], d2["mu_vec"][0], d2["mean_vec"][0]],
        y=[d2["x"][1], d2["mu_vec"][1], d2["mean_vec"][1]],
        mode="markers", marker=dict(size=10, color=[C["ink"], C["mu"], C["ink"]],
                                    line=dict(width=2, color="#fcfcfb")),
        text=["X", "μ𝟏", "x̄𝟏"], hovertemplate="%{text} = (%{x:.2f}, %{y:.2f})<extra></extra>",
        showlegend=False))

    _o = [0.0, 0.0]
    _ann = [
        _arrow(_o, d2["x"], C["mean"], 2.5),  # X itself
        _arrow(_o, d2["mu_vec"], C["mu"]),  # μ1
        _arrow(_o, d2["mean_vec"], C["mean"], 2),  # x̄1
        _arrow(d2["mu_vec"], d2["x"], C["err"]),  # error
        _arrow(d2["mean_vec"], d2["x"], C["res"]),  # residual
        _arrow(d2["mu_vec"], d2["mean_vec"], C["shift"], 5),  # shift along 1
        _label(d2["x"], "X", C["mean"], xshift=-18, yshift=14),
        _label(d2["mu_vec"], "μ𝟏  (0 DoF)", C["mu"], xshift=48, yshift=-14),
        _label(d2["mean_vec"], "x̄𝟏  (1 DoF)", C["mean"], xshift=48, yshift=-22),
        _label((d2["mu_vec"] + d2["x"]) / 2, "X − μ𝟏  error", C["err"], yshift=18),
        _label((d2["mean_vec"] + d2["x"]) / 2, "X − x̄𝟏  residual", C["res"], xshift=-70),
        _label((d2["mu_vec"] + d2["mean_vec"]) / 2, "(x̄ − μ)𝟏", C["shift"], xshift=40, yshift=-8),
    ]

    fig2d = go.Figure(_traces)
    fig2d.update_layout(
        annotations=_ann, template="plotly_white", height=620,
        margin=dict(l=40, r=20, t=40, b=40),
        xaxis=dict(title="x₁", range=[_lo, _hi], zeroline=True, zerolinecolor=C["guide"],
                   gridcolor="#eeede9", constrain="domain"),
        yaxis=dict(title="x₂", range=[_lo, _hi], scaleanchor="x", scaleratio=1,
                   zeroline=True, zerolinecolor=C["guide"], gridcolor="#eeede9"),
        legend=dict(orientation="h", y=1.04, x=0, font=dict(size=12)),
        paper_bgcolor="#fcfcfb", plot_bgcolor="#fcfcfb",
    )
    fig2d
    return (d2,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## n = 3 — the residual lives in a plane

    Same construction one dimension up. The line spanned by $\mathbf{1}$ is
    now the body diagonal of the cube; everything perpendicular to it is a
    **plane** ($x_1 + x_2 + x_3 = \text{const}$), drawn translucent through
    $\bar{x}\mathbf{1}$. The residual is pinned to that plane, so it carries
    two free numbers — $n-1 = 2$ — while the error vector can point
    anywhere in three.

    The camera starts looking straight at the triangle (along the normal of
    the plane spanned by $\mathbf{1}$ and the residual), so the picture is
    the 2-D one again — that is the point: for **any** $n$, these three
    vectors always lie in one plane. Rotate the scene to see the third
    dimension; with the cloud on, the red residual dots form a flat disc in
    the plane perpendicular to $\mathbf{1}$ (edge-on from the starting
    camera, so they look like a line) while the blue samples stay a blob.
    """)
    return


@app.cell(hide_code=True)
def _(
    C,
    cloud,
    decompose,
    face_on_camera,
    go,
    mu,
    n_cloud,
    np,
    outward,
    right_angle,
    seed,
    show_cloud,
    sigma,
    x1,
    x2,
    x3,
):
    d3 = decompose([x1.value, x2.value, x3.value], mu.value)

    def _arrow3(tail, tip, color, width=6, head=0.22):
        tail, tip = np.asarray(tail, float), np.asarray(tip, float)
        v = tip - tail
        ln = np.linalg.norm(v)
        if ln < 1e-9:
            return []
        u = v / ln
        shaft_end = tip - u * min(head, 0.5 * ln)
        line = go.Scatter3d(x=[tail[0], shaft_end[0]], y=[tail[1], shaft_end[1]], z=[tail[2], shaft_end[2]],
                            mode="lines", line=dict(color=color, width=width),
                            hoverinfo="skip", showlegend=False)
        cone = go.Cone(x=[tip[0]], y=[tip[1]], z=[tip[2]], u=[u[0]], v=[u[1]], w=[u[2]],
                       anchor="tip", sizemode="absolute", sizeref=head,
                       colorscale=[[0, color], [1, color]], showscale=False, hoverinfo="skip")
        return [line, cone]

    def _label3(pos, text, color):
        return go.Scatter3d(x=[pos[0]], y=[pos[1]], z=[pos[2]], mode="text", text=[text],
                            textposition="middle center", textfont=dict(size=13, color=color),
                            hoverinfo="skip", showlegend=False)

    _pts = [d3["x"], d3["mu_vec"], d3["mean_vec"], [0, 0, 0]]
    _cl = None
    if show_cloud.value:
        _cl = cloud(d3, sigma.value, n_cloud.value, seed.value)
        _pts += [_cl[0].min(0), _cl[0].max(0), _cl[1].min(0), _cl[1].max(0)]
    _all = np.array(_pts, dtype=float)
    _lo, _hi = _all.min() - 0.7, _all.max() + 0.7
    _L = max(abs(_lo), abs(_hi))

    _traces = []
    # Guide: line spanned by 1.
    _traces.append(go.Scatter3d(x=[-_L, _L], y=[-_L, _L], z=[-_L, _L], mode="lines",
                                line=dict(color=C["guide"], width=3, dash="dash"),
                                hoverinfo="skip", name="line spanned by 𝟏"))
    # Guide: the plane ⊥ 1 through x̄1, spanned by e1, e2.
    _c = d3["mean_vec"]
    _e1 = np.array([1, -1, 0]) / np.sqrt(2)
    _e2 = np.array([1, 1, -2]) / np.sqrt(6)
    _s = 0.55 * (_hi - _lo)
    _corners = np.array([_c + a * _s * _e1 + b * _s * _e2 for a, b in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])
    _traces.append(go.Mesh3d(x=_corners[:, 0], y=_corners[:, 1], z=_corners[:, 2],
                             i=[0, 0], j=[1, 2], k=[2, 3], color=C["res"], opacity=0.12,
                             hoverinfo="skip", name="plane ⊥ 𝟏 through x̄𝟏 (2 DoF)", showlegend=True))
    if _cl is not None:
        _traces.append(go.Scatter3d(x=_cl[0][:, 0], y=_cl[0][:, 1], z=_cl[0][:, 2], mode="markers",
                                    marker=dict(size=3.5, color=C["err"], opacity=0.5),
                                    name="samples X (fill the space)",
                                    hovertemplate="X = (%{x:.2f}, %{y:.2f}, %{z:.2f})<extra></extra>"))
        _traces.append(go.Scatter3d(x=_cl[1][:, 0], y=_cl[1][:, 1], z=_cl[1][:, 2], mode="markers",
                                    marker=dict(size=3.5, color=C["res"], opacity=0.6),
                                    name="residuals, tails at μ𝟏 (one plane)",
                                    hovertemplate="μ𝟏 + resid = (%{x:.2f}, %{y:.2f}, %{z:.2f})<extra></extra>"))
    _sq = right_angle(d3, 0.1 * (_hi - _lo))
    _traces.append(go.Scatter3d(x=_sq[:, 0], y=_sq[:, 1], z=_sq[:, 2], mode="lines",
                                line=dict(color=C["ink"], width=3), hoverinfo="skip", showlegend=False))
    _o = [0, 0, 0]
    _traces += _arrow3(_o, d3["x"], C["mean"], 5)
    _traces += _arrow3(_o, d3["mu_vec"], C["mu"])
    _traces += _arrow3(_o, d3["mean_vec"], C["mean"], 4)
    _traces += _arrow3(d3["mu_vec"], d3["x"], C["err"])
    _traces += _arrow3(d3["mean_vec"], d3["x"], C["res"])
    _traces += _arrow3(d3["mu_vec"], d3["mean_vec"], C["shift"], 9)
    _dv, _ds = 0.09 * (_hi - _lo), 0.16 * (_hi - _lo)  # vertex / side label nudges
    _traces += [
        _label3(outward(d3, d3["x"], _dv), "X", C["ink"]),
        _label3(outward(d3, d3["mu_vec"], _dv), "μ𝟏 (0 DoF)", C["mu"]),
        _label3(outward(d3, d3["mean_vec"], _dv), "x̄𝟏 (1 DoF)", C["ink"]),
        _label3(outward(d3, (d3["mu_vec"] + d3["x"]) / 2, _ds), "X − μ𝟏 error (3 DoF)", C["err"]),
        _label3(outward(d3, (d3["mean_vec"] + d3["x"]) / 2, _ds), "X − x̄𝟏 residual (2 DoF)", C["res"]),
        _label3(outward(d3, (d3["mu_vec"] + d3["mean_vec"]) / 2, _ds), "(x̄ − μ)𝟏", "#b07800"),
    ]
    _traces.append(go.Scatter3d(
        x=[d3["x"][0], d3["mu_vec"][0], d3["mean_vec"][0]],
        y=[d3["x"][1], d3["mu_vec"][1], d3["mean_vec"][1]],
        z=[d3["x"][2], d3["mu_vec"][2], d3["mean_vec"][2]],
        mode="markers", marker=dict(size=5, color=[C["ink"], C["mu"], C["ink"]]),
        text=["X", "μ𝟏", "x̄𝟏"], hovertemplate="%{text} = (%{x:.2f}, %{y:.2f}, %{z:.2f})<extra></extra>",
        showlegend=False))

    _ax = dict(range=[_lo, _hi], backgroundcolor="#fcfcfb", gridcolor="#e6e5e0",
               zerolinecolor=C["guide"], showspikes=False)
    fig3d = go.Figure(_traces)
    fig3d.update_layout(
        template="plotly_white", height=680, margin=dict(l=0, r=0, t=30, b=0),
        scene=dict(xaxis=dict(title="x₁", **_ax), yaxis=dict(title="x₂", **_ax), zaxis=dict(title="x₃", **_ax),
                   aspectmode="cube", camera=dict(eye=face_on_camera(d3))),
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=12)),
        paper_bgcolor="#fcfcfb",
    )
    fig3d
    return (d3,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Pythagoras on the triangle

    Because the residual is perpendicular to $\mathbf{1}$, the squared lengths
    add:

    $$
    \underbrace{\|X - \mu\mathbf{1}\|^2}_{\color{#2a78d6}{\text{error}}}
    \;=\;
    \underbrace{\|X - \bar{x}\mathbf{1}\|^2}_{\color{#e34948}{\text{residual}}}
    \;+\;
    \underbrace{\|(\bar{x}-\mu)\mathbf{1}\|^2}_{\color{#eda100}{n(\bar{x}-\mu)^2}}
    $$

    Check it on the current slider values (a dot product of exactly zero is
    the right angle):
    """)
    return


@app.cell(hide_code=True)
def _(d2, d3, mo):
    def _row(d):
        e2 = float(d["err"] @ d["err"])
        r2 = float(d["resid"] @ d["resid"])
        s2 = float(d["shift"] @ d["shift"])
        return (
            f"| {d['n']} | {d['xbar']:.3f} | {e2:.4f} | {r2:.4f} | {s2:.4f} "
            f"| {r2 + s2:.4f} | {float(d['resid'] @ d['one']):+.1e} |"
        )

    mo.md(
        "| n | x̄ | ‖X−μ𝟏‖² | ‖X−x̄𝟏‖² | n(x̄−μ)² | residual² + shift² | resid · 𝟏 |\n"
        "|---|---|---|---|---|---|---|\n" + _row(d2) + "\n" + _row(d3)
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## The whiteboard question: how to get $\mathbb{E}[\text{statistic}] = \sigma^2$

    Take expectations of the three squared lengths. Each coordinate of the
    error vector is an independent $N(0, \sigma^2)$, so its squared length
    is a sum of $n$ such squares:

    $$
    \mathbb{E}\big[\|\color{#2a78d6}{X-\mu\mathbf{1}}\|^2\big] = n\sigma^2
    \qquad
    \mathbb{E}\big[\|\color{#eda100}{(\bar{x}-\mu)\mathbf{1}}\|^2\big]
      = n\,\mathrm{Var}(\bar{x}) = n\cdot\frac{\sigma^2}{n} = \sigma^2
    $$

    Pythagoras then forces the third one:

    $$
    \mathbb{E}\big[\|\color{#e34948}{X-\bar{x}\mathbf{1}}\|^2\big]
      = n\sigma^2 - \sigma^2 = (n-1)\,\sigma^2 .
    $$

    The residual "lost" exactly one $\sigma^2$ — the one direction (along
    $\mathbf{1}$) the sample mean projected away. So the scale factor
    $\alpha$ on the whiteboard that makes
    $\mathbb{E}[\alpha\,\|X-\bar{x}\mathbf{1}\|^2] = \sigma^2$ is

    $$
    \alpha = \frac{1}{n-1}
    \qquad\Longrightarrow\qquad
    s^2 = \frac{1}{n-1}\sum_i (x_i - \bar{x})^2 \text{ is unbiased.}
    $$

    Dividing by $n$ instead would give $\tfrac{n-1}{n}\sigma^2$: too small by
    exactly one degree of freedom's worth. Monte-Carlo check with the current
    $\sigma$ (20 000 samples each):
    """)
    return


@app.cell(hide_code=True)
def _(mo, np, sigma):
    _rng = np.random.default_rng(42)
    _s = sigma.value
    _rows = []
    for _n in (2, 3):
        _xs = _rng.normal(0.0, _s, size=(20_000, _n))
        _xbar = _xs.mean(axis=1, keepdims=True)
        _err2 = (_xs**2).sum(axis=1).mean()
        _res2 = ((_xs - _xbar) ** 2).sum(axis=1).mean()
        _shift2 = (_n * _xbar[:, 0] ** 2).mean()
        _rows.append(
            f"| {_n} | {_err2:.3f} | {_n * _s**2:.3f} | {_res2:.3f} | {(_n - 1) * _s**2:.3f} "
            f"| {_shift2:.3f} | {_s**2:.3f} | {_res2 / (_n - 1):.3f} | {_res2 / _n:.3f} |"
        )
    mo.md(
        "| n | mean ‖error‖² | nσ² | mean ‖residual‖² | (n−1)σ² | mean n(x̄−μ)² | σ² "
        "| ‖residual‖²/(n−1) | ‖residual‖²/n |\n"
        "|---|---|---|---|---|---|---|---|---|\n" + "\n".join(_rows)
        + f"\n\nTarget σ² = **{_s**2:.3f}**. The $(n-1)$ column lands on it; the $n$ "
        f"column is short by the factor $(n-1)/n$ — half of it at $n=2$."
    )
    return


if __name__ == "__main__":
    app.run()
