"""Frame protocol parsing and raw-count -> pressure conversion (no I/O, no plotting)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

N_CH = 16
DEFAULT_RREF = 10_000.0
NO_LOAD_RATIO = 0.003  # ratio below this counts as "no load" (ADC noise floor)
MAX_RATIO = 0.99       # avoid division by zero when a sensor is shorted


@dataclass
class Frame:
    seq: int
    t_ms: int
    vdd_mv: int
    raw: np.ndarray  # shape (16,), counts per firmware channel


@dataclass
class Info:
    fw_version: str
    channels: int
    rref: float
    fpc_map: List[int]


def parse_info(line: str) -> Optional[Info]:
    """I,restride-heatmap,<fw>,channels=16,rref=10000,map=2-3-4-..."""
    parts = line.strip().split(",")
    if len(parts) < 3 or parts[0] != "I" or parts[1] != "restride-heatmap":
        return None
    kv = dict(p.split("=", 1) for p in parts[3:] if "=" in p)
    try:
        return Info(
            fw_version=parts[2],
            channels=int(kv.get("channels", N_CH)),
            rref=float(kv.get("rref", DEFAULT_RREF)),
            fpc_map=[int(v) for v in kv.get("map", "").split("-") if v],
        )
    except ValueError:
        return None


def parse_frame(line: str) -> Optional[Frame]:
    """F,<seq>,<t_ms>,<vdd_mv>,<r0>..<r15>; returns None for anything malformed."""
    parts = line.strip().split(",")
    if len(parts) != 4 + N_CH or parts[0] != "F":
        return None
    try:
        vals = [int(p) for p in parts[1:]]
    except ValueError:
        return None
    return Frame(vals[0], vals[1], vals[2], np.array(vals[3:], dtype=np.float64))


ADC_FULL_MV = 3600.0  # 0.9 V internal reference / gain 1/4 (must match the firmware overlay)
ADC_COUNTS = 4096     # 12-bit single-ended full scale


def vdd_raw_from_mv(vdd_mv: float) -> float:
    """Firmware reports vdd_mv = vdd_count * ADC_FULL_MV / ADC_COUNTS; invert it."""
    return vdd_mv / ADC_FULL_MV * ADC_COUNTS


def conductance_ms(raw: np.ndarray, vdd_raw: float, rref: float) -> np.ndarray:
    """Pressure index = sensor conductance in mS.

    Divider: V = VDD * Rref / (Rref + Rs)  ->  ratio = V/VDD = raw / vdd_raw
    Rs = Rref * (1 - ratio) / ratio  ->  G = 1/Rs = ratio / (Rref * (1 - ratio)).
    vdd_raw is the SAADC count of the VDD channel (same gain/reference as the bus channels),
    so supply and ADC-scale errors cancel.
    """
    if vdd_raw <= 0:
        return np.zeros_like(raw)
    ratio = np.clip(raw / vdd_raw, 0.0, MAX_RATIO)
    g = ratio / (rref * (1.0 - ratio)) * 1e3
    g[ratio < NO_LOAD_RATIO] = 0.0
    return g


def load_layout(path: str, mirror: bool = False):
    """Returns (fpc_pins ordered by channel, xy array (16,2), outline (M,2), regions)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = sorted(data["sensors"].items(), key=lambda kv: kv[1]["ch"])
    if [v["ch"] for _, v in items] != list(range(N_CH)):
        raise ValueError("layout.json must define channels 0..15 exactly once")
    pins = [int(k) for k, _ in items]
    xy = np.array([[v["x"], v["y"]] for _, v in items], dtype=np.float64)
    outline = np.array(data["outline"], dtype=np.float64)
    regions = [v.get("region", "") for _, v in items]
    if mirror:
        xy[:, 0] = 1.0 - xy[:, 0]
        outline[:, 0] = 1.0 - outline[:, 0]
    return pins, xy, outline, regions


DEFAULT_LAYOUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "layout.json")
