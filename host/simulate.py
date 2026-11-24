"""Fake frame generator that follows a walking gait; no hardware needed.

    python simulate.py                 # print I/F lines to stdout at 50 Hz
    python simulate.py --port COM9     # write them to a (virtual) serial port
    python heatmap.py --sim            # in-process, used by the viewer

Gait (per cycle): heel strike (pins 4,5) -> midfoot (13,15,17,18) -> forefoot (7,12,16,20)
-> toe-off (8,9,10) -> swing (no load).
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Iterator

import numpy as np

from frames import DEFAULT_RREF, load_layout, DEFAULT_LAYOUT

VDD_MV = 3300
ADC_FULL_MV = 3600.0  # 0.9 V reference / gain 1/4
ADC_COUNTS = 4096

# (pins, centre time as fraction of cycle, width, peak sensor conductance in mS)
PHASES = [
    ([4, 5],            0.08, 0.06, 0.09),
    ([13, 15, 17, 18],  0.24, 0.09, 0.05),
    ([7, 12, 16, 20],   0.42, 0.09, 0.08),
    ([8, 9, 10],        0.56, 0.06, 0.07),
]


def info_line(fpc_pins) -> str:
    return "I,restride-heatmap,sim,channels=16,rref=%d,map=%s" % (
        DEFAULT_RREF, "-".join(str(p) for p in fpc_pins))


def frames(rate_hz: float = 50.0, cycle_s: float = 1.2, noise: bool = True,
           layout: str = DEFAULT_LAYOUT) -> Iterator[str]:
    """Yield F lines forever (no sleeping; the caller paces)."""
    pins, _, _, _ = load_layout(layout)
    rng = np.random.default_rng(1)
    vdd_raw = VDD_MV / ADC_FULL_MV * ADC_COUNTS
    seq = 0
    while True:
        t = seq / rate_hz
        phase = (t % cycle_s) / cycle_s
        g = np.zeros(16)
        for plist, centre, width, peak in PHASES:
            w = np.exp(-0.5 * ((phase - centre) / width) ** 2)
            for p in plist:
                g[pins.index(p)] += peak * w
        # conductance (mS) -> sensor R -> divider ratio -> counts
        with np.errstate(divide="ignore"):
            rs = np.where(g > 1e-4, 1e3 / np.maximum(g, 1e-9), 1e9)
        ratio = DEFAULT_RREF / (DEFAULT_RREF + rs)
        raw = ratio * vdd_raw
        if noise:
            raw = raw + rng.normal(0, 1.5, 16)
        raw = np.clip(np.round(raw), 0, 4095).astype(int)
        yield "F,%d,%d,%d,%s" % (seq, int(t * 1000), VDD_MV, ",".join(map(str, raw)))
        seq += 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", help="serial port to write to (default: stdout)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--rate", type=float, default=50.0)
    ap.add_argument("--layout", default=DEFAULT_LAYOUT)
    a = ap.parse_args()

    pins, _, _, _ = load_layout(a.layout)
    if a.port:
        import serial
        out = serial.Serial(a.port, a.baud)
        write = lambda s: out.write((s + "\n").encode())
    else:
        write = lambda s: (sys.stdout.write(s + "\n"), sys.stdout.flush())

    write(info_line(pins))
    nxt = time.perf_counter()
    for line in frames(a.rate, layout=a.layout):
        write(line)
        nxt += 1.0 / a.rate
        time.sleep(max(0.0, nxt - time.perf_counter()))


if __name__ == "__main__":
    main()
