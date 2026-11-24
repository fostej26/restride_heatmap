"""Live plantar-pressure heatmap for the ReStride 16-sensor insole.

    python heatmap.py --sim                    # no hardware
    python heatmap.py                          # auto-detect the DK's VCOM port
    python heatmap.py --port COM7 --baud 115200 --log out.csv

Keys: t tare | s PNG snapshot | r start/stop CSV recording | v toggle live values | q quit
"""
from __future__ import annotations

import argparse
import collections
import csv
import queue
import sys
import threading
import time
from typing import Iterator, Optional

import matplotlib
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.path import Path
from scipy.interpolate import RBFInterpolator

import frames as fr

GRID_NX, GRID_NY = 100, 250
Y_ASPECT = GRID_NY / GRID_NX  # insole is roughly 1 : 2.5 (width : length)
TRAIL_LEN = 60
COP_MIN_MS = 0.002  # total conductance (mS) below which the COP is not drawn


# --------------------------------------------------------------------------- sources
def serial_lines(port: str, baud: int) -> Iterator[str]:
    import serial
    with serial.Serial(port, baud, timeout=1) as ser:
        while True:
            raw = ser.readline()
            if raw:
                yield raw.decode("ascii", errors="ignore")


def detect_port(baud: int, seconds: float = 2.5) -> str:
    """Try each serial port (J-Link VCOMs first) and return the one speaking our protocol."""
    import serial
    from serial.tools import list_ports

    ports = sorted(list_ports.comports(),
                   key=lambda p: 0 if (p.vid == 0x1366 or "J-Link" in (p.description or "")) else 1)
    for p in ports:
        try:
            with serial.Serial(p.device, baud, timeout=0.3) as ser:
                end = time.time() + seconds
                while time.time() < end:
                    line = ser.readline().decode("ascii", errors="ignore")
                    # The I line is sent at boot and repeated every few seconds; F lines also count.
                    if fr.parse_info(line) or line.startswith("F,"):
                        return p.device
        except (serial.SerialException, OSError):
            continue
    raise SystemExit("No restride-heatmap port found. Pass --port COMx (is the DK flashed and "
                     "no other terminal holding the port?).")


def sim_lines(layout: str) -> Iterator[str]:
    import simulate
    pins, _, _, _ = fr.load_layout(layout)
    yield simulate.info_line(pins)
    nxt = time.perf_counter()
    for line in simulate.frames(50.0, layout=layout):
        yield line
        nxt += 1 / 50.0
        time.sleep(max(0.0, nxt - time.perf_counter()))


# --------------------------------------------------------------------------- viewer
class Viewer:
    def __init__(self, args, lines: Iterator[str]):
        self.args = args
        self.pins, self.xy, self.outline, _ = fr.load_layout(args.layout, args.left)
        self.rref = fr.DEFAULT_RREF
        self.q: "queue.Queue[str]" = queue.Queue(maxsize=2000)
        self.stop = threading.Event()
        threading.Thread(target=self._reader, args=(lines,), daemon=True).start()

        self.g = np.zeros(fr.N_CH)       # smoothed conductance (mS)
        self.tare = np.zeros(fr.N_CH)
        self.last_seq: Optional[int] = None
        self.dropped = 0
        self.n_frames = 0
        self.stamps = collections.deque(maxlen=100)
        self.trail = collections.deque(maxlen=TRAIL_LEN)
        self.last_frame: Optional[fr.Frame] = None
        self.csv_file = None
        self.csv_writer = None
        self.show_values = False
        self._build_grid()
        self._build_figure()
        if args.log:
            self._start_recording(args.log)

    # --- input thread
    def _reader(self, lines):
        try:
            for line in lines:
                if self.stop.is_set():
                    return
                try:
                    self.q.put_nowait(line)
                except queue.Full:
                    pass
        except Exception as e:  # serial unplugged etc.
            print("reader stopped:", e, file=sys.stderr)

    # --- interpolation: thin-plate RBF is linear in the data, so build the 16->grid matrix once
    def _build_grid(self):
        gx, gy = np.meshgrid(np.linspace(0, 1, GRID_NX), np.linspace(0, 1, GRID_NY))
        pts = np.column_stack([gx.ravel(), gy.ravel()])
        self.mask = Path(self.outline).contains_points(pts).reshape(GRID_NY, GRID_NX)
        inside = pts[self.mask.ravel()]
        rbf = RBFInterpolator(self.xy, np.eye(fr.N_CH), kernel="thin_plate_spline", smoothing=1e-3)
        self.basis = rbf(inside)  # (n_inside, 16)

    def _grid(self, values: np.ndarray) -> np.ndarray:
        img = np.full((GRID_NY, GRID_NX), np.nan)
        img[self.mask] = np.clip(self.basis @ values, 0.0, None)
        return img

    # --- figure
    def _build_figure(self):
        self.fig, self.ax = plt.subplots(figsize=(5.2, 9), constrained_layout=True)
        self.fig.canvas.manager.set_window_title("ReStride insole heatmap")
        cmap = plt.get_cmap("inferno").copy()
        cmap.set_bad(alpha=0)
        self.im = self.ax.imshow(self._grid(np.zeros(fr.N_CH)), origin="lower", extent=(0, 1, 0, 1),
                                 aspect=Y_ASPECT, cmap=cmap, vmin=0, vmax=self.args.vmax,
                                 interpolation="bilinear")
        cb = self.fig.colorbar(self.im, ax=self.ax, fraction=0.05, pad=0.02)
        cb.set_label("pressure index: sensor conductance (mS)")
        closed = np.vstack([self.outline, self.outline[:1]])
        self.ax.plot(closed[:, 0], closed[:, 1], color="0.6", lw=1.2)
        self.ax.scatter(self.xy[:, 0], self.xy[:, 1], s=14, c="white", edgecolors="0.2", zorder=3)
        self.pin_labels = []
        self.val_labels = []
        for (x, y), pin in zip(self.xy, self.pins):
            self.pin_labels.append(self.ax.text(x, y + 0.015, str(pin), ha="center", va="bottom",
                                                fontsize=8, color="white", zorder=4))
            self.val_labels.append(self.ax.text(x, y - 0.015, "", ha="center", va="top", fontsize=7,
                                                color="cyan", zorder=4))
        (self.trail_line,) = self.ax.plot([], [], color="cyan", lw=1.2, alpha=0.7, zorder=5)
        (self.cop_dot,) = self.ax.plot([], [], "o", ms=9, mfc="none", mec="cyan", mew=2, zorder=6)
        self.ax.set_xlim(-0.03, 1.03)
        self.ax.set_ylim(-0.03, 1.03)
        self.ax.set_facecolor("#111")
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        edge = "lateral" if not self.args.left else "medial"
        other = "medial" if not self.args.left else "lateral"
        self.ax.set_xlabel("%s  <-    ->  %s" % (other, edge), fontsize=8)
        self.info = self.ax.text(0.02, 0.995, "", transform=self.ax.transAxes, va="top",
                                 fontsize=8, family="monospace", color="white",
                                 bbox=dict(fc="black", ec="none", alpha=0.55))
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self.fig.canvas.mpl_connect("close_event", lambda _e: self.stop.set())
        self.anim = FuncAnimation(self.fig, self._tick, interval=1000 // 30, blit=False,
                                  cache_frame_data=False)

    # --- keys
    def _on_key(self, ev):
        if ev.key == "t":
            self.tare = self.g + self.tare
            self.g[:] = 0
        elif ev.key == "s":
            name = time.strftime("heatmap_%Y%m%d_%H%M%S.png")
            self.fig.savefig(name, dpi=150)
            print("saved", name)
        elif ev.key == "r":
            if self.csv_file:
                self._stop_recording()
            else:
                self._start_recording(time.strftime("restride_%Y%m%d_%H%M%S.csv"))
        elif ev.key == "v":
            self.show_values = not self.show_values
        elif ev.key == "q":
            self.stop.set()
            plt.close(self.fig)

    def _start_recording(self, path):
        self.csv_file = open(path, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(["seq", "t_ms", "vdd_mv"] + ["raw%d" % i for i in range(fr.N_CH)])
        print("recording to", path)

    def _stop_recording(self):
        if self.csv_file:
            self.csv_file.close()
            print("recording stopped")
        self.csv_file = self.csv_writer = None

    # --- frame handling
    def _handle(self, f: fr.Frame):
        if self.last_seq is not None and f.seq != self.last_seq + 1:
            self.dropped += max(0, f.seq - self.last_seq - 1)
        self.last_seq = f.seq
        self.n_frames += 1
        self.stamps.append(time.perf_counter())
        self.last_frame = f
        vdd_raw = fr.vdd_raw_from_mv(f.vdd_mv)
        g = fr.conductance_ms(f.raw, vdd_raw, self.rref) - self.tare
        g = np.clip(g, 0.0, None)
        a = self.args.smooth
        self.g = a * g + (1 - a) * self.g
        if self.csv_writer:
            self.csv_writer.writerow([f.seq, f.t_ms, f.vdd_mv] + [int(v) for v in f.raw])

    def _tick(self, _i):
        got = 0
        while got < 200:
            try:
                line = self.q.get_nowait()
            except queue.Empty:
                break
            got += 1
            info = fr.parse_info(line)
            if info:
                self.rref = info.rref
                continue
            f = fr.parse_frame(line)
            if f:
                self._handle(f)
        self._draw()
        if self.args.snapshot_after and self.n_frames >= self.args.snapshot_after:
            self.fig.savefig(self.args.snapshot_path, dpi=120)
            print("snapshot saved:", self.args.snapshot_path)
            self.stop.set()
            plt.close(self.fig)
        return []

    def _draw(self):
        self.im.set_data(self._grid(self.g))
        total = float(self.g.sum())
        if total > COP_MIN_MS:
            c = (self.g[:, None] * self.xy).sum(axis=0) / total
            self.trail.append(c)
            arr = np.array(self.trail)
            self.trail_line.set_data(arr[:, 0], arr[:, 1])
            self.cop_dot.set_data([c[0]], [c[1]])
        else:
            self.trail.clear()
            self.trail_line.set_data([], [])
            self.cop_dot.set_data([], [])
        for lab, v in zip(self.val_labels, self.g):
            lab.set_text("%.3f" % v if self.show_values else "")
        fps = 0.0
        if len(self.stamps) > 2 and self.stamps[-1] > self.stamps[0]:
            fps = (len(self.stamps) - 1) / (self.stamps[-1] - self.stamps[0])
        self.info.set_text("load %.3f mS   %.0f fps   dropped %d%s" % (
            total, fps, self.dropped, "   REC" if self.csv_file else ""))

    def run(self):
        plt.show()
        self.stop.set()
        self._stop_recording()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", help="serial port (default: auto-detect)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--sim", action="store_true", help="use the built-in gait simulator")
    ap.add_argument("--left", action="store_true", help="left insole: mirror x -> 1 - x")
    ap.add_argument("--layout", default=fr.DEFAULT_LAYOUT)
    ap.add_argument("--log", help="start recording raw frames to this CSV")
    ap.add_argument("--vmax", type=float, default=0.1, help="colour scale max, mS (default 0.1)")
    ap.add_argument("--smooth", type=float, default=0.6, help="EMA weight of the newest frame, 0-1")
    ap.add_argument("--snapshot-after", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--snapshot-path", default="snapshot.png", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.sim:
        lines = sim_lines(args.layout)
    else:
        port = args.port or detect_port(args.baud)
        print("using", port)
        lines = serial_lines(port, args.baud)
    Viewer(args, lines).run()


if __name__ == "__main__":
    main()
