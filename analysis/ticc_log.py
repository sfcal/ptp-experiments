"""Parse TAPR TICC capture logs into phase data for the notebooks here.

Handles the log shapes ticc-capture.sh / picocom produce:

* ``# ...`` banner and menu lines (skipped; the ``Measurement Mode``,
  ``Timestamp Wrap`` and ``Channel Names`` lines are read for context).
* Time Interval / Period lines: one float per line, ``ch1 - ch0`` seconds.
* Timestamp lines: ``<seconds> chX`` -- one event per channel per line.
* An optional ``\\t<ISO 8601>`` GPS tag appended by ticc-capture.sh.

Timestamp events are turned back into A->B intervals by pairing each ch0
event with the nearest ch1 event, so every notebook keeps seeing one phase
reading per second whatever mode the TICC was in. Each channel's events are
also kept on their own as phase against the TICC's 10 MHz EXT_REF
(``channel_phase``), ready for allantools with ``data_type="phase"``. Files
that switch mode mid-capture (a DTR reset after a menu change) are handled
line by line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

_MODE_RE = re.compile(r"^#\s*Measurement Mode:\s*(.+?)\s*$")
_WRAP_RE = re.compile(r"^#\s*Timestamp Wrap:\s*(\d+)")
_NAMES_RE = re.compile(r"^#\s*Channel Names:\s*(\S)/(\S)")
_CH_RE = re.compile(r"^ch(\S)$")


@dataclass
class TiccLog:
    """One parsed capture. ``phase`` is what the notebooks analyse."""

    phase: np.ndarray                    # seconds, file order
    modes: list[str] = field(default_factory=list)   # banner modes, in order
    wrap: int = 0                        # digits before wrap (0 = none)
    channels: tuple[str, str] = ("A", "B")           # (ch0, ch1) names
    n_interval: int = 0                  # readings taken from interval lines
    n_events: dict[str, int] = field(default_factory=dict)  # per channel
    n_paired: int = 0                    # intervals derived from event pairs
    n_unpaired: int = 0                  # events dropped for lack of a partner
    single_channel: str | None = None    # set when phase is one channel vs EXT_REF
    # Per-channel phase vs EXT_REF, seconds: timestamp minus the nominal
    # pulse time (index * tau0), wrap undone. Keys are channel names.
    channel_phase: dict[str, np.ndarray] = field(default_factory=dict)
    channel_tau0: dict[str, float] = field(default_factory=dict)

    def describe(self) -> str:
        parts = [f"{self.phase.size} readings"]
        if self.n_interval:
            parts.append(f"{self.n_interval} interval lines")
        if self.n_events:
            ev = ", ".join(f"ch{c}={n}" for c, n in self.n_events.items())
            parts.append(f"timestamp events {ev}")
            if self.single_channel:
                parts.append(f"ch{self.single_channel} alone: phase vs EXT_REF")
            else:
                parts.append(f"{self.n_paired} pairs, {self.n_unpaired} unpaired")
            if self.channel_tau0:
                cad = ", ".join(f"ch{c} τ₀={t:g} s" for c, t in self.channel_tau0.items())
                parts.append(f"per-channel phase vs EXT_REF ({cad})")
        if self.wrap and self.n_events:
            parts.append(f"wrap 10^{self.wrap} s unwrapped")
        return "; ".join(parts)


def parse_ticc(data: bytes | str, pair_window: float | None = None) -> TiccLog:
    """Parse a whole log. ``pair_window`` is the largest |ch1 - ch0| accepted
    as one pair, in seconds; default is half the ch0 spacing."""
    if isinstance(data, bytes):
        # Serial captures can contain garbage bytes; decode leniently.
        data = data.decode(errors="ignore")

    modes: list[str] = []
    wrap = 0
    names = ("A", "B")
    intervals: list[tuple[int, float]] = []          # (line no, value)
    events: dict[str, list[tuple[int, float]]] = {}  # chan -> (line no, t)

    for lineno, line in enumerate(data.splitlines()):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            if m := _MODE_RE.match(s):
                modes.append(m.group(1))
            elif m := _WRAP_RE.match(s):
                wrap = int(m.group(1))
            elif m := _NAMES_RE.match(s):
                names = (m.group(1), m.group(2))
            continue
        tok = s.split()
        try:
            val = float(tok[0])
        except ValueError:
            continue  # partial first/last lines, menu echoes, etc.
        if len(tok) > 1 and (m := _CH_RE.match(tok[1])):
            events.setdefault(m.group(1), []).append((lineno, val))
        else:
            intervals.append((lineno, val))

    log = TiccLog(
        phase=np.empty(0), modes=modes, wrap=wrap, channels=names,
        n_interval=len(intervals),
        n_events={c: len(v) for c, v in events.items()},
    )

    readings: list[tuple[int, float]] = list(intervals)
    for _c, _ev in events.items():
        _t, _ = _unwrap(_ev, wrap)
        _a = np.asarray([t for _, t in _t])
        if _a.size >= 2:
            log.channel_phase[_c], log.channel_tau0[_c] = _phase_vs_ref(_a)
    if events:
        ch0, ch1 = names
        if ch0 not in events or ch1 not in events:
            # Fall back to order of appearance if the banner was missing.
            seen = list(events)
            ch0 = seen[0] if ch0 not in events else ch0
            others = [c for c in seen if c != ch0]
            ch1 = others[0] if others else None
        t0, log.wrap = _unwrap(events[ch0], wrap)
        if ch1 is None:
            readings += _single_channel_phase(t0)
            log.single_channel = ch0
        else:
            t1, _ = _unwrap(events[ch1], wrap)
            paired, unpaired = _pair(t0, t1, pair_window)
            readings += paired
            log.n_paired, log.n_unpaired = len(paired), unpaired
            log.channels = (ch0, ch1)

    readings.sort(key=lambda r: r[0])
    log.phase = np.asarray([v for _, v in readings], dtype=float)
    return log


def load_ticc(path, **kw) -> TiccLog:
    with open(path, "rb") as f:
        return parse_ticc(f.read(), **kw)


def _unwrap(ev: list[tuple[int, float]], wrap: int) -> tuple[list[tuple[int, float]], int]:
    """Undo the TICC's odometer wrap (10**wrap s) so timestamps increase.

    With ``wrap`` unknown (no banner in the file) a backwards step infers
    the modulus from the integer digits of the last raw value, which is how
    the TICC defines its wrap setting. Returns the events and the wrap
    digits actually used (0 if no wrap was seen)."""
    modulus = 10.0 ** wrap if wrap else None
    out, off, raw_prev = [], 0.0, None
    for lineno, t in ev:
        if raw_prev is not None and t < raw_prev:
            if modulus is None:
                wrap = len(str(int(raw_prev)))
                modulus = 10.0 ** wrap
            off += modulus
        raw_prev = t
        out.append((lineno, t + off))
    return out, (wrap if off else 0)


def _pair(t0, t1, window):
    """Match each ch0 event to the nearest ch1 event within ``window``.
    Returns [(line no of ch0 event, t1 - t0)], count of dropped events."""
    a = np.asarray([t for _, t in t0])
    b = np.asarray([t for _, t in t1])
    if window is None:
        window = 0.5 * float(np.median(np.diff(a))) if a.size > 1 else 0.5
    order = np.argsort(b, kind="stable")
    b_sorted = b[order]
    used = np.zeros(b.size, dtype=bool)
    paired = []
    for (lineno, _), ta in zip(t0, a):
        j = int(np.searchsorted(b_sorted, ta))
        best = None
        for k in (j - 1, j):
            if 0 <= k < b.size and not used[k]:
                d = abs(b_sorted[k] - ta)
                if d <= window and (best is None or d < best[0]):
                    best = (d, k)
        if best is None:
            continue
        used[best[1]] = True
        paired.append((lineno, float(b_sorted[best[1]] - ta)))
    unpaired = (a.size - len(paired)) + int((~used).sum())
    return paired, unpaired


def _phase_vs_ref(a: np.ndarray) -> tuple[np.ndarray, float]:
    """Timestamps of one channel against their nominal cadence: the phase of
    that channel relative to the TICC's 10 MHz EXT_REF. Pulse index comes
    from the timestamp itself, so a missed pulse leaves a gap in the index,
    not a step in the phase. Returns (phase seconds, tau0 seconds)."""
    tau0 = float(f"{np.median(np.diff(a)):.3g}")  # 1 PPS -> exactly 1.0
    n = np.round((a - a[0]) / tau0)
    return a - a[0] - n * tau0, tau0


def _single_channel_phase(t0):
    """One channel only: use its phase vs EXT_REF as the file's phase."""
    a = np.asarray([t for _, t in t0])
    if a.size < 2:
        return [(ln, 0.0) for ln, _ in t0]
    phase, _ = _phase_vs_ref(a)
    return [(ln, float(p)) for (ln, _), p in zip(t0, phase)]
