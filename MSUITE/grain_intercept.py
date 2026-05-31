"""
grain_intercept.py  —  Interactive ASTM E112 grain size intercept counter
==========================================================================
Masters thesis: AZ91 / AZ80 magnesium alloy grain size analysis

Usage:
    python grain_intercept.py
    A method dialog opens (Linear / Circular), then a file dialog.

Controls (both modes):
    Left-click            → single intercept  (count += 1.0)   [green]
    Right-click           → tangent hit        (count += 0.5)   [yellow]
    Middle-click          → triple-point hit   (count += 1.5)   [red]
    N key / Next Line btn → advance to next test line / circle
    B key / Prev Line btn → go back to previous line / circle (restores markers)
    Z key / Undo btn      → remove last marker on active feature
    Scroll wheel          → zoom in / out (centred on cursor)
    Middle-button drag    → pan
    R key                 → reset zoom to full image
    Close window          → exit without saving (no files written)

File naming:
    Magnification is read from the filename (e.g. "10x af.png").
    If not found the user is prompted and the file is renamed on disk.
    Output files include magnification tag: intercept_linear_<sample>_<mag>_r<N>_*.csv

Repeat grid strategy (linear method):
    Lines are placed using a periodic/cyclic scheme with N lines per orientation.
    spacing = image_dimension / N  (not N+1 — no dead margins at edges).
    Repeat r applies offset δ = (r-1)/5 × spacing, taken modulo the image dimension,
    so lines wrap around rather than falling off the edge.  Each repeat always has
    exactly LINES_PER_ORIENTATION lines per orientation, all full-length.
    Repeats 1–5 tile the inter-line space evenly at 0, 1/5, 2/5, 3/5, 4/5 spacing.

    Circular method: repeat enumeration only — no offset applied to circles.

Output (written only on Save):
    RESULTS_GRAIN_SIZE/<CastFull>/<Intermediate>/<Sample>/
        intercept_linear_<sample>_<mag>_r<N>_summary.csv
        intercept_linear_<sample>_<mag>_r<N>_detail.csv
      or
        intercept_circular_<sample>_<mag>_r<N>_summary.csv
        intercept_circular_<sample>_<mag>_r<N>_detail.csv

Cast map:  G → GC,   H → HPDC,   D → DCC

Image folder structure (under BASE_PATH):
    <CastLetter>/<Intermediate>/<Sample>/<file>
    e.g.  D/DC/DC19/10x af.png
"""

import os

# =============================================================================
# USER-TUNEABLE PARAMETERS  ← edit these freely
# =============================================================================
# ---INSTRUCTIONS ---
# Please set BASE_DIR to the folder where you extracted the Magnesium Masters Project data.
BASE_DIR = r"C:\Path\To\Project"

BASE_PATH    = os.path.join(BASE_DIR, "ANALYSED", "Etched")
RESULTS_BASE = os.path.join(BASE_DIR, "RESULTS_GRAIN_SIZE")
# Pixel-to-micrometre ratios keyed by magnification
PX_PER_UM = {
    2.5:  0.522,
    5.0:  1.045,
    10.0: 2.09,
    20.0: 4.18,
    50.0: 10.45,
    100.0:20.9,
}

# Scale-bar length (µm) burned into each image — displayed to user for check
SCALEBAR_UM_LABEL = {
    2.5:  500,
    5.0:  200,
    10.0: 100,
    20.0: 50,
    50.0: 20,
    100.0:10,
}

# Top-left pixel of the scale-bar region; everything right+below is excluded
SCALEBAR_ORIGIN = {
    2.5:  (2805, 2000),
    5.0:  (2857, 2000),
    10.0: (2857, 2000),
    20.0: (2857, 2000),
    50.0: (2857, 2000),
    100.0:(2857, 2000),
}

# Approximate largest grain diameter (µm) per cast letter — sets circle sizing
GRAIN_SIZE_APPROX_UM = {
    "G": 1000.0,   # GC
    "H":   30.0,   # HPDC (solutionised, 20x)
    "D":  200.0,   # DCC
}

# Override which sample is used for grain size analysis per cast type.
# None  → standard naming convention applies (GS, HS, DS).
# str   → use this specific sample name instead.
# HS is overetched and cannot be re-done; HA4 is used as a proxy
# (150 °C, 4 hrs — no DP precipitation and no grain growth expected at this
# temperature per literature, so grain size is representative of solutionised state).
GRAIN_SAMPLE_OVERRIDE = {
    "GC":   None,    # → GS
    "HPDC": "HA4",   # → HA4  (proxy for HS)
    "DCC":  "DA4",    # → DS
}

# Concentric circles are placed at these multiples of the approximate grain diameter
CIRCLE_MULTIPLIERS = [1, 2, 3]   # ← easy to change

# Number of test lines per orientation (H, V, D+, D-)
LINES_PER_ORIENTATION = 5        # ← easy to change

# Snap tolerance: click must be within this many µm of the active line/circle
SNAP_RADIUS_UM = 8.0

# Zoom factor per scroll-wheel tick
ZOOM_FACTOR = 1.25
# =============================================================================

import sys
import os
import re
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Button
from PIL import Image
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from datetime import datetime
import subprocess
import tempfile

# Fixed demo output root — persists across sessions until explicitly wiped
DEMO_RESULTS_BASE = os.path.join(tempfile.gettempdir(), "msuite_demo",
                                 "RESULTS_GRAIN_SIZE")

# ── Cast map ──────────────────────────────────────────────────────────────────
CAST_MAP = {"G": "GC", "H": "HPDC", "D": "DCC"}

# ── Magnification patterns — checked longest-first to avoid 5x inside 50x ────
MAG_ORDER = [100.0, 50.0, 20.0, 10.0, 5.0, 2.5]
MAG_PATTERNS = {
    100.0: re.compile(r"100x",           re.IGNORECASE),
    50.0:  re.compile(r"50x",            re.IGNORECASE),
    20.0:  re.compile(r"20x",            re.IGNORECASE),
    10.0:  re.compile(r"10x",            re.IGNORECASE),
    5.0:   re.compile(r"(?<![.\d])5x",    re.IGNORECASE),
    2.5:   re.compile(r"2\.5x",          re.IGNORECASE),
}

# ── Visual colours ────────────────────────────────────────────────────────────
COL_SINGLE  = "#4CAF50"   # green  – single intercept
COL_TANGENT = "#FFC107"   # yellow – tangent (×0.5)
COL_TRIPLE  = "#F44336"   # red    – triple point (×1.5)
COL_ACTIVE  = "#E53935"   # red    – active feature
COL_DONE    = "#546E7A"   # grey   – completed feature
COL_PENDING = "#37474F"   # dark   – not yet reached
COL_EXCL    = "#FF6600"   # orange – scale-bar zone

MARKER_RADIUS_PX = 6      # display radius of intercept dots

# ── Click mappings ────────────────────────────────────────────────────────────
# Left-click  → single intercept  (×1.0)
# Right-click → triple point      (×1.5)
# T key       → tangent hit       (×0.5)  — toggled via keyboard, snapped to cursor
KIND_MAP   = {1: "single", 3: "triple"}
WEIGHT_MAP = {"single": 1.0, "tangent": 0.5, "triple": 1.5}
COLOUR_MAP = {"single": COL_SINGLE, "tangent": COL_TANGENT, "triple": COL_TRIPLE}


# =============================================================================
# FILE / PATH HELPERS
# =============================================================================

def mag_to_str(mag):
    """Return canonical filename tag: 2.5 → '2.5x', 10.0 → '10x'."""
    if mag == 2.5:
        return "2.5x"
    return f"{mag:g}x"


def pick_method():
    """Modal dialog to choose Linear or Circular method."""
    root = tk.Tk()
    root.withdraw()
    root.call("wm", "attributes", ".", "-topmost", True)

    choice = {"value": None}

    dlg = tk.Toplevel(root)
    dlg.title("Select Intercept Method")
    dlg.resizable(False, False)
    root.call("wm", "attributes", str(dlg), "-topmost", True)

    tk.Label(dlg, text="Select ASTM E112 intercept method:",
             font=("Arial", 11), pady=10).pack(padx=20)

    def _set(v):
        choice["value"] = v
        dlg.destroy()

    tk.Button(dlg, text="Linear  (Heyn §13)",
              width=26, command=lambda: _set("linear")).pack(pady=4, padx=20)
    tk.Button(dlg, text="Circular  (Abrams §14.3)",
              width=26, command=lambda: _set("circular")).pack(pady=4, padx=20)
    tk.Button(dlg, text="Cancel",
              width=26, command=dlg.destroy).pack(pady=(4, 14), padx=20)

    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
    root.wait_window(dlg)
    root.destroy()
    return choice["value"]


def pick_image(initial_dir):
    root = tk.Tk()
    root.withdraw()
    root.call("wm", "attributes", ".", "-topmost", True)
    path = filedialog.askopenfilename(
        title="Select etched grain image",
        initialdir=initial_dir if os.path.isdir(initial_dir) else os.path.expanduser("~"),
        filetypes=[("Image files", "*.png *.tif *.tiff *.jpg *.jpeg *.bmp"),
                   ("All files",   "*.*")],
    )
    root.destroy()
    return path if path else None


def parse_magnification(filepath):
    """Return magnification as float or None."""
    name = os.path.basename(filepath)
    for mag in MAG_ORDER:
        if MAG_PATTERNS[mag].search(name):
            return mag
    return None


def prompt_magnification_and_rename(abs_path):
    """Prompt user, rename file, return (new_path, mag) or (None, None)."""
    valid_str = ["2.5x", "5x", "10x", "20x", "50x", "100x"]
    lookup    = {s: float(s.replace("x", "")) for s in valid_str}
    lookup["2.5x"] = 2.5

    root = tk.Tk()
    root.withdraw()
    root.call("wm", "attributes", ".", "-topmost", True)

    mag_str = simpledialog.askstring(
        "Magnification not found",
        f"Magnification not detected in filename.\n"
        f"Enter one of: {', '.join(valid_str)}",
        parent=root,
    )
    root.destroy()

    if not mag_str:
        return None, None

    mag_str = mag_str.strip().lower()
    if mag_str not in lookup:
        root2 = tk.Tk(); root2.withdraw()
        messagebox.showerror("Invalid entry",
                             f"'{mag_str}' not recognised.\nValid: {', '.join(valid_str)}")
        root2.destroy()
        return None, None

    mag      = lookup[mag_str]
    directory = os.path.dirname(abs_path)
    old_name  = os.path.basename(abs_path)
    new_name  = f"{mag_str} {old_name}"
    new_path  = os.path.join(directory, new_name)
    os.rename(abs_path, new_path)
    print(f"[INFO] Renamed '{old_name}' → '{new_name}'")
    return new_path, mag


def derive_relative_parts(abs_image_path, base_path):
    abs_img  = os.path.normcase(os.path.abspath(abs_image_path))
    abs_base = os.path.normcase(os.path.abspath(base_path))
    if not abs_img.startswith(abs_base):
        raise ValueError(
            f"Image is not inside BASE_PATH.\n"
            f"  Image : {abs_image_path}\n"
            f"  Base  : {base_path}"
        )
    rel   = os.path.relpath(abs_img, abs_base)
    parts = rel.split(os.sep)
    if len(parts) < 4:
        raise ValueError(
            f"Expected <Cast>/<Intermediate>/<Sample>/<file>, got: {rel}"
        )
    return parts[0].upper(), parts[1].upper(), parts[2].upper()


def derive_output_dir(cast_letter, intermediate, sample_name, results_base):
    cast_full = CAST_MAP.get(cast_letter, cast_letter)
    return os.path.join(results_base, cast_full, intermediate, sample_name)


def next_repeat_number(output_dir, sample_name, method_tag, mag_tag):
    """Return next repeat number, independent per (sample, method, magnification)."""
    pattern = re.compile(
        rf"^intercept_{re.escape(method_tag)}_{re.escape(sample_name)}"
        rf"_{re.escape(mag_tag)}_r(\d+)_summary\.csv$",
        re.IGNORECASE,
    )
    if not os.path.isdir(output_dir):
        return 1
    nums = [int(m.group(1)) for f in os.listdir(output_dir)
            if (m := pattern.match(f))]
    return max(nums) + 1 if nums else 1


def load_image(path):
    try:
        return np.array(Image.open(path))
    except FileNotFoundError:
        print(f"[ERROR] Image not found: {path}")
        sys.exit(1)


# =============================================================================
# GEOMETRY: LINEAR TEST LINES  —  periodic/cyclic repeat grid
# =============================================================================

def _clip_line_to_rect(slope, intercept, w, h):
    """Clip infinite line y = slope*x + intercept to rectangle [0,w]×[0,h].
    Returns (p1, p2) or None."""
    TOL = 1e-6
    pts = []
    y = intercept
    if -TOL <= y <= h + TOL:
        pts.append((0.0, max(0.0, min(h, y))))
    y = slope * w + intercept
    if -TOL <= y <= h + TOL:
        pts.append((float(w), max(0.0, min(h, y))))
    if slope != 0:
        x = -intercept / slope
        if -TOL <= x <= w + TOL:
            pts.append((max(0.0, min(w, x)), 0.0))
        x = (h - intercept) / slope
        if -TOL <= x <= w + TOL:
            pts.append((max(0.0, min(w, x)), float(h)))
    pts = list({(round(p[0], 4), round(p[1], 4)) for p in pts})
    pts.sort()
    if len(pts) < 2:
        return None
    if math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 1.0:
        return None
    return pts[0], pts[-1]


def _line_intersects_scalebar(p1, p2, sb_x, sb_y, img_w, img_h):
    sx1, sy1 = min(p1[0], p2[0]), min(p1[1], p2[1])
    sx2, sy2 = max(p1[0], p2[0]), max(p1[1], p2[1])
    if sx2 < sb_x or sx1 > img_w:
        return False
    if sy2 < sb_y or sy1 > img_h:
        return False
    return True


def _clip_endpoint_to_scalebar(p1, p2, sb_x, sb_y):
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    t_min = 1.0
    if dx > 0:
        t = (sb_x - x1) / dx
        if 0.0 <= t <= 1.0:
            yt = y1 + t * dy
            if yt >= sb_y:
                t_min = min(t_min, t)
    if dy > 0:
        t = (sb_y - y1) / dy
        if 0.0 <= t <= 1.0:
            xt = x1 + t * dx
            if xt >= sb_x:
                t_min = min(t_min, t)
    return (x1 + t_min * dx, y1 + t_min * dy)


def _apply_scalebar_clip(p1, p2, sb_x, sb_y, img_w, img_h):
    if _line_intersects_scalebar(p1, p2, sb_x, sb_y, img_w, img_h):
        return p1, _clip_endpoint_to_scalebar(p1, p2, sb_x, sb_y)
    return p1, p2


def build_linear_grid(img_w, img_h, sb_x, sb_y, n_per_orient, px_per_um, repeat_num):
    """
    Build H, V, D+, D- test lines using a periodic/cyclic repeat grid.

    Spacing = image_dimension / n_per_orient  (exact tiling, no dead margins).
    Repeat r shifts all positions by δ = (r-1)/5 × spacing, mod image_dimension,
    so lines wrap rather than falling off the edge.  Each repeat always has
    exactly n_per_orient lines per orientation.

    Returns list of feature dicts.
    """
    iw = float(img_w)
    ih = float(img_h)
    r  = repeat_num
    lines = []
    idx   = 0

    def periodic_positions(total, n, delta_frac):
        """
        Return n evenly-spaced positions tiling [0, total) with cyclic offset.
        Base positions: (i + 0.5) * spacing  for i in 0..n-1
        Offset applied: δ = delta_frac * spacing, taken mod total.
        """
        spacing = total / n
        delta   = delta_frac * spacing
        return [((i + 0.5) * spacing + delta) % total for i in range(n)]

    delta_frac = (r - 1) / 5.0   # 0, 0.2, 0.4, 0.6, 0.8 for repeats 1–5

    # ── Horizontal lines (y fixed) ─────────────────────────────────────────
    for y in sorted(periodic_positions(ih, n_per_orient, delta_frac)):
        p1 = (0.0, y)
        p2 = (iw,  y)
        p1, p2 = _apply_scalebar_clip(p1, p2, sb_x, sb_y, iw, ih)
        length_px = abs(p2[0] - p1[0])
        if length_px < 1.0:
            continue
        lines.append({
            "orientation": "H", "p1": p1, "p2": p2,
            "length_px": length_px, "length_um": length_px / px_per_um,
            "index": idx,
        })
        idx += 1

    # ── Vertical lines (x fixed) ───────────────────────────────────────────
    for x in sorted(periodic_positions(iw, n_per_orient, delta_frac)):
        p1 = (x, 0.0)
        p2 = (x, ih)
        p1, p2 = _apply_scalebar_clip(p1, p2, sb_x, sb_y, iw, ih)
        length_px = abs(p2[1] - p1[1])
        if length_px < 1.0:
            continue
        lines.append({
            "orientation": "V", "p1": p1, "p2": p2,
            "length_px": length_px, "length_um": length_px / px_per_um,
            "index": idx,
        })
        idx += 1

    # ── Diagonal D+ (slope +1): characterised by intercept b = y - x ──────
    # Perpendicular spacing along the anti-diagonal direction = diag / n
    # Intercepts tile [-(ih), iw] cyclically (length = iw + ih)
    diag_total = iw + ih
    for b_frac in sorted(periodic_positions(diag_total, n_per_orient, delta_frac)):
        b      = b_frac - ih          # shift so b spans [-ih, iw)
        result = _clip_line_to_rect(1.0, b, iw, ih)
        if result is None:
            continue
        p1, p2 = result
        p1, p2 = _apply_scalebar_clip(p1, p2, sb_x, sb_y, iw, ih)
        length_px = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
        if length_px < 1.0:
            continue
        lines.append({
            "orientation": "D+", "p1": p1, "p2": p2,
            "length_px": length_px, "length_um": length_px / px_per_um,
            "index": idx,
        })
        idx += 1

    # ── Diagonal D- (slope -1): intercept b = y + x ─────────────────────
    # Intercepts tile [0, iw + ih] cyclically
    for b_frac in sorted(periodic_positions(diag_total, n_per_orient, delta_frac)):
        b      = b_frac               # spans [0, iw + ih)
        result = _clip_line_to_rect(-1.0, b, iw, ih)
        if result is None:
            continue
        p1, p2 = result
        p1, p2 = _apply_scalebar_clip(p1, p2, sb_x, sb_y, iw, ih)
        length_px = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
        if length_px < 1.0:
            continue
        lines.append({
            "orientation": "D-", "p1": p1, "p2": p2,
            "length_px": length_px, "length_um": length_px / px_per_um,
            "index": idx,
        })
        idx += 1

    return lines


def snap_to_line(px, py, feat):
    """Project (px,py) onto line segment. Return (sx,sy), distance."""
    x1, y1 = feat["p1"]
    x2, y2 = feat["p2"]
    dx, dy  = x2 - x1, y2 - y1
    if dx == dy == 0:
        return (x1, y1), math.hypot(px - x1, py - y1)
    t  = max(0.0, min(1.0, ((px-x1)*dx + (py-y1)*dy) / (dx*dx + dy*dy)))
    sx = x1 + t * dx
    sy = y1 + t * dy
    return (sx, sy), math.hypot(px - sx, py - sy)


# =============================================================================
# GEOMETRY: CIRCULAR TEST FEATURES
# =============================================================================

def build_circular_grid(img_w, img_h, sb_x, sb_y, cast_letter, px_per_um):
    """
    Build three concentric circles centred in the active area.
    Circular repeats use the same circle layout — only the repeat number changes.
    """
    grain_um  = GRAIN_SIZE_APPROX_UM.get(cast_letter, 200.0)
    aw, ah    = float(sb_x), float(sb_y)
    cx, cy    = aw / 2.0, ah / 2.0
    max_r_px  = min(cx, cy) * 0.90
    max_r_um  = max_r_px / px_per_um

    min_r_um  = grain_um
    warnings  = []

    if min_r_um >= max_r_um:
        warnings.append(
            f"Approximate grain size ({grain_um:.0f} µm) equals or exceeds 90 % "
            f"of the active image radius ({max_r_um:.1f} µm). "
            f"All circles have been capped to fit the image."
        )
        min_r_um = max_r_um * 0.33

    radii_um = [
        min_r_um,
        (min_r_um + max_r_um) / 2.0,
        max_r_um,
    ]

    circles = []
    for i, r_um in enumerate(radii_um):
        r_px = r_um * px_per_um
        if r_px > max_r_px:
            r_px = max_r_px
            r_um = r_px / px_per_um
        circles.append({
            "radius_um":        r_um,
            "radius_px":        r_px,
            "cx": cx, "cy": cy,
            "circumference_um": 2 * math.pi * r_um,
            "multiplier":       i + 1,
            "index":            i,
        })

    return circles, warnings


def snap_to_circle(px, py, feat):
    """Project (px,py) onto circle boundary. Return (sx,sy), distance."""
    cx, cy = feat["cx"], feat["cy"]
    r      = feat["radius_px"]
    dx, dy = px - cx, py - cy
    d      = math.hypot(dx, dy)
    if d == 0:
        return (cx + r, cy), r
    sx = cx + r * dx / d
    sy = cy + r * dy / d
    return (sx, sy), abs(d - r)


# =============================================================================
# INTERCEPT RECORD
# =============================================================================

class InterceptRecord:
    def __init__(self, feature_index):
        self.feature_index = feature_index
        self.events = []    # list of {"x_px","y_px","weight","type"}

    def add(self, x, y, weight, kind):
        self.events.append({"x_px": x, "y_px": y, "weight": weight, "type": kind})

    def remove_last(self):
        if self.events:
            return self.events.pop()
        return None

    @property
    def total_count(self):
        return sum(e["weight"] for e in self.events)

    @property
    def n_events(self):
        return len(self.events)


# =============================================================================
# MAIN TOOL
# =============================================================================

class GrainInterceptTool:

    def __init__(self, abs_image_path, mag, sample_name,
                 cast_letter, intermediate, method, repeat_num, demo=False):
        self.abs_image_path = abs_image_path
        self.mag            = mag
        self.mag_tag        = mag_to_str(mag)
        self.sample_name    = sample_name
        self.cast_letter    = cast_letter
        self.intermediate   = intermediate
        self.method         = method
        self.repeat_num     = repeat_num
        self.px_per_um      = PX_PER_UM[mag]
        self.sb_origin      = SCALEBAR_ORIGIN[mag]
        self.scored_at      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.demo           = demo

        self.img    = load_image(abs_image_path)
        self.img_h, self.img_w = self.img.shape[:2]

        sb_x, sb_y = self.sb_origin

        if method == "linear":
            self.features   = build_linear_grid(
                self.img_w, self.img_h, sb_x, sb_y,
                LINES_PER_ORIENTATION, self.px_per_um, repeat_num)
            self.method_tag = "linear"
        else:
            self.features, circ_warnings = build_circular_grid(
                self.img_w, self.img_h, sb_x, sb_y,
                cast_letter, self.px_per_um)
            self.method_tag = "circular"
            if circ_warnings:
                root = tk.Tk(); root.withdraw()
                messagebox.showwarning("Circle size warning",
                                       "\n\n".join(circ_warnings))
                root.destroy()

        self.records          = [InterceptRecord(i) for i in range(len(self.features))]
        self.active_idx       = 0
        self._feature_artists = []
        self._marker_artists  = []   # list-of-lists; inner list per feature

        # Pan state
        self._pan_mode     = False
        self._pan_active   = False
        self._pan_start    = None
        self._xlim_start   = None
        self._ylim_start   = None

        self._build_figure()

    # =========================================================================
    # FIGURE
    # =========================================================================

    def _build_figure(self):
        mag_str  = self.mag_tag
        sb_label = SCALEBAR_UM_LABEL[self.mag]

        self.fig = plt.figure(figsize=(16, 10))
        self.fig.patch.set_facecolor("#1a1a1a")
        try:
            self.fig.canvas.toolbar.pack_forget()
        except Exception:
            pass

        STRIP_IN   = 0.95
        STRIP_FRAC = STRIP_IN / self.fig.get_figheight()
        IMG_B      = STRIP_FRAC + 0.004

        self.ax = self.fig.add_axes([0.0, IMG_B, 1.0, 1.0 - IMG_B])
        self.ax.set_facecolor("#1a1a1a")
        self.ax.imshow(self.img, origin="upper", interpolation="nearest")
        self.ax.set_xlim(0, self.img_w)
        self.ax.set_ylim(self.img_h, 0)
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.axis("off")

        self._xlim_full = (0.0, float(self.img_w))
        self._ylim_full = (float(self.img_h), 0.0)

        # Scale-bar exclusion shading
        sb_x, sb_y = self.sb_origin
        self.ax.add_patch(mpatches.Rectangle(
            (sb_x, sb_y), self.img_w - sb_x, self.img_h - sb_y,
            linewidth=1, edgecolor=COL_EXCL, facecolor=COL_EXCL,
            alpha=0.22, zorder=2,
        ))

        # Draw features
        if self.method == "linear":
            self._draw_linear_features()
        else:
            self._draw_circular_features()

        # ── Control strip ──────────────────────────────────────────────────
        self.ax_strip = self.fig.add_axes([0.0, 0.0, 1.0, STRIP_FRAC])
        self.ax_strip.set_facecolor("#111111")
        self.ax_strip.axis("off")

        method_label = ("Linear (Heyn §13)"
                        if self.method == "linear"
                        else "Circular (Abrams §14.3)")
        info = (
            f"{self.sample_name}  |  {os.path.basename(self.abs_image_path)}  |  "
            f"Mag: {mag_str}  |  Scale bar label: {sb_label} µm  |  "
            f"{self.px_per_um:.3f} px/µm  |  Method: {method_label}  |  "
            f"Repeat: r{self.repeat_num}  |  "
            f"Scroll=zoom   P=pan   R=reset   N=next   B=prev   Z=undo   T=tangent"
        )
        self.ax_strip.text(
            0.005, 0.97, info,
            transform=self.ax_strip.transAxes,
            color="#90CAF9", fontsize=7.5, va="top", family="monospace",
            clip_on=False,
        )

        self.status_text = self.ax_strip.text(
            0.005, 0.58, "",
            transform=self.ax_strip.transAxes,
            color="white", fontsize=8.5, va="top", family="monospace",
            clip_on=False,
        )

        self.pan_indicator = self.ax_strip.text(
            0.5, 0.55, "",
            transform=self.ax_strip.transAxes,
            color="#FFD600", fontsize=9, va="top", family="monospace",
            fontweight="bold", ha="center", clip_on=False,
        )

        self._update_status()

        # Legend
        legend_elems = [
            mpatches.Patch(facecolor=COL_SINGLE,  label="Single intercept [L-click]  ×1.0"),
            mpatches.Patch(facecolor=COL_TANGENT, label="Tangent hit [T key]  ×0.5"),
            mpatches.Patch(facecolor=COL_TRIPLE,  label="Triple point [R-click]  ×1.5"),
            mpatches.Patch(facecolor=COL_ACTIVE,  label="Active feature"),
            mpatches.Patch(facecolor=COL_DONE,    label="Completed"),
            mpatches.Patch(facecolor=COL_EXCL,    label="Scale bar zone", alpha=0.5),
        ]
        self.ax_strip.legend(
            handles=legend_elems, loc="lower left",
            bbox_to_anchor=(0.0, 0.0), ncol=6, fontsize=7,
            framealpha=0, labelcolor="white",
            handlelength=1.0, handleheight=0.6,
            handletextpad=0.4, borderpad=0.2,
            columnspacing=0.8, borderaxespad=0.2,
        )

        # ── Buttons ────────────────────────────────────────────────────────
        BTN_H = STRIP_FRAC * 0.78
        BTN_Y = (STRIP_FRAC - BTN_H) / 2
        GAP   = 0.007
        RIGHT = 0.995

        def make_btn(left, w, label, col, hover, callback, fontsize=8):
            ax = self.fig.add_axes([left, BTN_Y, w, BTN_H])
            btn = Button(ax, label, color=col, hovercolor=hover)
            btn.label.set_color("white")
            btn.label.set_fontsize(fontsize)
            btn.on_clicked(callback)
            return btn

        self.btn_save = make_btn(RIGHT-0.10, 0.10,
                                 "Save Results", "#37474F", "#546E7A", self._on_save)

        next_label = "Next Line [N]" if self.method == "linear" else "Next Circle [N]"
        self.btn_next = make_btn(RIGHT-0.10-GAP-0.10, 0.10,
                                 next_label, "#1A3A4A", "#1F5070", self._on_next)

        prev_label = "Prev Line [B]" if self.method == "linear" else "Prev Circle [B]"
        self.btn_prev = make_btn(RIGHT-0.10-GAP-0.10-GAP-0.10, 0.10,
                                 prev_label, "#1A3A4A", "#1F5070", self._on_prev)

        self.btn_undo = make_btn(RIGHT-0.10-GAP-0.10-GAP-0.10-GAP-0.08, 0.08,
                                 "Undo [Z]", "#4A2020", "#6D2E2E", self._on_undo)

        self.btn_view = make_btn(
            RIGHT-0.10-GAP-0.10-GAP-0.10-GAP-0.08-GAP-0.09, 0.09,
            "Reset View [R]", "#1a1a1a", "#2a2a2a",
            lambda e: self._reset_view())

        # Events
        c = self.fig.canvas
        c.mpl_connect("button_press_event",   self._on_press)
        c.mpl_connect("button_release_event", self._on_release)
        c.mpl_connect("motion_notify_event",  self._on_motion)
        c.mpl_connect("scroll_event",         self._on_scroll)
        c.mpl_connect("key_press_event",      self._on_key)
        c.mpl_connect("close_event",          self._on_close)

        n_feat    = len(self.features)
        feat_noun = "lines" if self.method == "linear" else "circles"
        try:
            self.fig.canvas.manager.set_window_title(
                f"Grain Intercept — {self.sample_name} — {mag_str} — "
                f"r{self.repeat_num} — {method_label} — {n_feat} {feat_noun}"
            )
        except Exception:
            pass

        self._refresh_feature_colours()

    # =========================================================================
    # DRAW FEATURES
    # =========================================================================

    def _draw_linear_features(self):
        for feat in self.features:
            x1, y1 = feat["p1"]
            x2, y2 = feat["p2"]
            artist, = self.ax.plot(
                [x1, x2], [y1, y2],
                color=COL_PENDING, linewidth=1.2,
                alpha=0.6, zorder=3, solid_capstyle="butt",
            )
            self._feature_artists.append(artist)
            self._marker_artists.append([])

    def _draw_circular_features(self):
        for feat in self.features:
            patch = mpatches.Circle(
                (feat["cx"], feat["cy"]), feat["radius_px"],
                fill=False, edgecolor=COL_PENDING,
                linewidth=1.5, alpha=0.6, zorder=3,
            )
            self.ax.add_patch(patch)
            self._feature_artists.append(patch)
            self._marker_artists.append([])

    def _refresh_feature_colours(self):
        for i, artist in enumerate(self._feature_artists):
            if i < self.active_idx:
                col, alpha, lw = COL_DONE,    0.35, 0.8
            elif i == self.active_idx:
                col, alpha, lw = COL_ACTIVE,  1.00, 1.5
            else:
                col, alpha, lw = COL_PENDING, 0.45, 0.8

            if self.method == "linear":
                artist.set_color(col)
                artist.set_alpha(alpha)
                artist.set_linewidth(lw)
            else:
                artist.set_edgecolor(col)
                artist.set_alpha(alpha)
                artist.set_linewidth(lw)

        # Refresh marker visibility: current feature full opacity, others dim
        for i, dots in enumerate(self._marker_artists):
            for dot in dots:
                if i == self.active_idx:
                    dot.set_alpha(0.9)
                    dot.set_zorder(5)
                else:
                    dot.set_alpha(0.35)
                    dot.set_zorder(4)

        self.fig.canvas.draw_idle()

    # =========================================================================
    # STATUS
    # =========================================================================

    def _update_status(self):
        n_feat     = len(self.features)
        rec        = self.records[self.active_idx]
        total_all  = sum(r.total_count for r in self.records)
        feat_noun  = "line" if self.method == "linear" else "circle"

        if self.method == "linear":
            detail = f"orient={self.features[self.active_idx]['orientation']}"
        else:
            detail = f"r={self.features[self.active_idx]['radius_um']:.1f} µm"

        self.status_text.set_text(
            f"Active {feat_noun}: {self.active_idx+1}/{n_feat}  ({detail})  |  "
            f"Intercepts on this {feat_noun}: {rec.total_count:.1f}  "
            f"({rec.n_events} events)  |  "
            f"Running total: {total_all:.1f}"
        )

    # =========================================================================
    # SNAP
    # =========================================================================

    def _snap(self, px, py):
        feat   = self.features[self.active_idx]
        snap_r = SNAP_RADIUS_UM * self.px_per_um

        if self.method == "linear":
            (sx, sy), dist = snap_to_line(px, py, feat)
        else:
            (sx, sy), dist = snap_to_circle(px, py, feat)

        return (sx, sy) if dist <= snap_r else None

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    def _on_press(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return

        if event.button == 1:
            if self._pan_mode:
                self._pan_active = True
                self._pan_start  = (event.xdata, event.ydata)
                self._xlim_start = self.ax.get_xlim()
                self._ylim_start = self.ax.get_ylim()
            else:
                snapped = self._snap(event.xdata, event.ydata)
                if snapped is None:
                    return
                self._add_marker(snapped[0], snapped[1], "single", 1.0)

        elif event.button == 3 and not self._pan_mode:
            snapped = self._snap(event.xdata, event.ydata)
            if snapped is None:
                return
            self._add_marker(snapped[0], snapped[1], "triple", 1.5)

    def _on_release(self, event):
        if event.button == 1:
            self._pan_active = False

    def _on_motion(self, event):
        if not self._pan_active:
            return
        if event.inaxes != self.ax or event.xdata is None:
            return
        dx = self._pan_start[0] - event.xdata
        dy = self._pan_start[1] - event.ydata
        x0, x1 = self._xlim_start
        y0, y1 = self._ylim_start
        self.ax.set_xlim(x0 + dx, x1 + dx)
        self.ax.set_ylim(y0 + dy, y1 + dy)
        self.fig.canvas.draw_idle()

    def _on_scroll(self, event):
        if event.inaxes != self.ax:
            return
        xd, yd = event.xdata, event.ydata
        if xd is None:
            return
        f = 1.0 / ZOOM_FACTOR if event.button == "up" else ZOOM_FACTOR
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        self.ax.set_xlim(xd + (x0-xd)*f, xd + (x1-xd)*f)
        self.ax.set_ylim(yd + (y0-yd)*f, yd + (y1-yd)*f)
        self.fig.canvas.draw_idle()

    def _on_key(self, event):
        key = event.key.lower() if event.key else ""
        if key == "r":
            self._reset_view()
        elif key == "p":
            self._toggle_pan_mode()
        elif key == "n":
            self._on_next(None)
        elif key == "b":
            self._on_prev(None)
        elif key == "z":
            self._on_undo(None)
        elif key == "t":
            # Tangent hit — snap to active feature at current cursor position
            if not self._pan_mode and event.inaxes == self.ax:
                xd, yd = self.ax.transData.inverted().transform(
                    (event.x, event.y)
                )
                snapped = self._snap(xd, yd)
                if snapped is not None:
                    self._add_marker(snapped[0], snapped[1], "tangent", 0.5)

    def _on_close(self, event):
        pass

    # =========================================================================
    # PAN MODE  (mirrors lom_score)
    # =========================================================================

    def _toggle_pan_mode(self):
        self._pan_mode   = not self._pan_mode
        self._pan_active = False

        if self._pan_mode:
            self.pan_indicator.set_text(
                "⬡  PAN MODE  —  drag to pan  |  P to exit  |  scoring disabled"
            )
            for sp in self.ax.spines.values():
                sp.set_edgecolor("#FFD600")
                sp.set_linewidth(2)
                sp.set_visible(True)
        else:
            self.pan_indicator.set_text("")
            for sp in self.ax.spines.values():
                sp.set_visible(False)

        self.fig.canvas.draw_idle()
        print(f"[INFO] Pan mode "
              f"{'ON — scoring disabled' if self._pan_mode else 'OFF — scoring enabled'}")

    # =========================================================================
    # MARKERS
    # =========================================================================

    def _add_marker(self, sx, sy, kind, weight):
        self.records[self.active_idx].add(sx, sy, weight, kind)
        dot = plt.Circle((sx, sy), MARKER_RADIUS_PX,
                          color=COLOUR_MAP[kind], zorder=5, alpha=0.9)
        self.ax.add_patch(dot)
        self._marker_artists[self.active_idx].append(dot)
        self._update_status()
        self.fig.canvas.draw_idle()

    def _on_undo(self, event):
        rec  = self.records[self.active_idx]
        dots = self._marker_artists[self.active_idx]
        if rec.n_events == 0 or not dots:
            return
        rec.remove_last()
        dots[-1].remove()
        dots.pop()
        self._update_status()
        self.fig.canvas.draw_idle()

    # =========================================================================
    # NEXT / PREV FEATURE
    # =========================================================================

    def _on_next(self, event):
        rec       = self.records[self.active_idx]
        feat_noun = "line" if self.method == "linear" else "circle"

        if rec.n_events == 0:
            root = tk.Tk(); root.withdraw()
            go   = messagebox.askyesno(
                "No intercepts marked",
                f"No intercepts marked on {feat_noun} {self.active_idx+1}.\n"
                f"Proceed to next {feat_noun} anyway?"
            )
            root.destroy()
            if not go:
                return

        n_feat = len(self.features)
        if self.active_idx < n_feat - 1:
            self.active_idx += 1
            self._refresh_feature_colours()
            self._update_status()
            self.fig.canvas.draw_idle()
        else:
            root = tk.Tk(); root.withdraw()
            messagebox.showinfo(
                "All features complete",
                f"All {n_feat} {feat_noun}s have been counted.\n"
                f"Press 'Save Results' when ready."
            )
            root.destroy()

    def _on_prev(self, event):
        """Go back to the previous feature, restoring its markers to full opacity."""
        if self.active_idx == 0:
            return   # already at first feature — nothing to go back to

        self.active_idx -= 1
        self._refresh_feature_colours()
        self._update_status()
        self.fig.canvas.draw_idle()

    # =========================================================================
    # RESET VIEW
    # =========================================================================

    def _reset_view(self):
        self.ax.set_xlim(self._xlim_full)
        self.ax.set_ylim(self._ylim_full)
        self.fig.canvas.draw_idle()

    # =========================================================================
    # SAVE
    # =========================================================================

    def _on_save(self, event=None):
        n_feat    = len(self.features)
        feat_noun = "lines" if self.method == "linear" else "circles"
        total     = sum(r.total_count for r in self.records)

        root = tk.Tk(); root.withdraw()

        if self.active_idx < n_feat - 1:
            proceed = messagebox.askyesno(
                "Incomplete count",
                f"Only {self.active_idx+1} of {n_feat} {feat_noun} have been reached.\n"
                f"Saving now produces an incomplete dataset.\n\nSave anyway?"
            )
            if not proceed:
                root.destroy()
                return

        demo_tag = "[DEMO] " if self.demo else ""
        save_note = ("Results will NOT be saved to disk.\n\n" if self.demo
                     else "")
        msg = (
            f"{save_note}"
            f"Sample       :  {self.sample_name}\n"
            f"Method       :  {self.method_tag}\n"
            f"Magnification:  {self.mag_tag}\n"
            f"Repeat       :  r{self.repeat_num}\n"
            f"Scored at    :  {self.scored_at}\n\n"
            f"Features used  :  {self.active_idx+1} / {n_feat}\n"
            f"Total intercept count  :  {total:.1f}\n\n"
            f"{'Run analysis on temporary data?' if self.demo else 'Save two CSV files (summary + detail)?'}"
        )
        title = f"{demo_tag}Confirm Save" if not self.demo else "Demo — Confirm Save"
        confirmed = messagebox.askyesno(title, msg)
        root.destroy()
        if not confirmed:
            return

        self._write_csvs()
        plt.close(self.fig)

    def _write_csvs(self):
        # ── Demo mode: redirect to temp directory ─────────────────────────
        if self.demo:
            output_dir = derive_output_dir(
                self.cast_letter, self.intermediate,
                self.sample_name, DEMO_RESULTS_BASE
            )
            os.makedirs(output_dir, exist_ok=True)
            print(f"[DEMO] Output dir → {output_dir}")
        else:
            output_dir = derive_output_dir(
                self.cast_letter, self.intermediate,
                self.sample_name, RESULTS_BASE
            )
            os.makedirs(output_dir, exist_ok=True)

        tag = (f"intercept_{self.method_tag}_{self.sample_name}"
               f"_{self.mag_tag}_r{self.repeat_num}")

        summary_path = os.path.join(output_dir, f"{tag}_summary.csv")
        detail_path  = os.path.join(output_dir, f"{tag}_detail.csv")

        # ── Summary CSV ────────────────────────────────────────────────────
        summary_rows = []
        for i, feat in enumerate(self.features):
            rec = self.records[i]
            row = {
                "feature_index":       i,
                "n_intercept_events":  rec.n_events,
                "total_count":         rec.total_count,
                "sample":              self.sample_name,
                "magnification":       self.mag,
                "mag_tag":             self.mag_tag,
                "px_per_um":           self.px_per_um,
                "method":              self.method_tag,
                "repeat":              self.repeat_num,
                "scored_at":           self.scored_at,
            }
            if self.method == "linear":
                row["orientation"] = feat["orientation"]
                row["length_px"]   = round(feat["length_px"], 2)
                row["length_um"]   = round(feat["length_um"], 4)
                row["NL_per_mm"]   = round(
                    (rec.total_count / feat["length_um"]) * 1000.0, 6
                ) if feat["length_um"] > 0 else 0.0
            else:
                row["radius_um"]        = round(feat["radius_um"], 4)
                row["circumference_um"] = round(feat["circumference_um"], 4)
                row["multiplier"]       = feat["multiplier"]
                row["approx_grain_um"]  = GRAIN_SIZE_APPROX_UM.get(
                                              self.cast_letter, 200.0)
                row["NL_per_mm"]        = round(
                    (rec.total_count / feat["circumference_um"]) * 1000.0, 6
                ) if feat["circumference_um"] > 0 else 0.0
            summary_rows.append(row)

        pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
        print(f"[INFO] Summary → {summary_path}")

        # ── Detail CSV ─────────────────────────────────────────────────────
        detail_rows = []
        for i, feat in enumerate(self.features):
            for ev in self.records[i].events:
                row = {
                    "feature_index": i,
                    "x_px":          round(ev["x_px"], 2),
                    "y_px":          round(ev["y_px"], 2),
                    "x_um":          round(ev["x_px"] / self.px_per_um, 4),
                    "y_um":          round(ev["y_px"] / self.px_per_um, 4),
                    "type":          ev["type"],
                    "weight":        ev["weight"],
                    "sample":        self.sample_name,
                    "magnification": self.mag,
                    "mag_tag":       self.mag_tag,
                    "method":        self.method_tag,
                    "repeat":        self.repeat_num,
                }
                if self.method == "linear":
                    row["orientation"] = feat["orientation"]
                else:
                    row["radius_um"]   = round(feat["radius_um"], 4)
                detail_rows.append(row)

        cols = ["feature_index", "x_px", "y_px", "x_um", "y_um",
                "type", "weight", "sample", "magnification", "mag_tag",
                "method", "repeat"]
        df_detail = pd.DataFrame(detail_rows) if detail_rows else pd.DataFrame(columns=cols)
        df_detail.to_csv(detail_path, index=False)
        print(f"[INFO] Detail  → {detail_path}")

        # Auto-launch grain_analyse.py on the summary CSV
        analyser_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "grain_analyse.py"
        )
        if os.path.isfile(analyser_path):
            cmd = [sys.executable, analyser_path, summary_path]
            if self.demo:
                cmd.append("--demo")
            subprocess.Popen(cmd)
            print(f"[INFO] Launched grain_analyse.py → {summary_path}")
        else:
            print(f"[WARN] grain_analyse.py not found alongside grain_intercept.py — "
                  f"run it manually.")

    # =========================================================================
    def run(self):
        plt.show()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    demo_mode = "--demo" in sys.argv
    if demo_mode:
        sys.argv.remove("--demo")
        print("[DEMO] Running in demo mode — no data will be saved to results.")

    method = pick_method()
    if method is None:
        print("[INFO] Cancelled — exiting.")
        sys.exit(0)

    abs_image_path = pick_image(BASE_PATH)
    if abs_image_path is None:
        print("[INFO] No file selected — exiting.")
        sys.exit(0)

    mag = parse_magnification(abs_image_path)
    if mag is None:
        abs_image_path, mag = prompt_magnification_and_rename(abs_image_path)
        if abs_image_path is None or mag is None:
            print("[INFO] Magnification entry cancelled — exiting.")
            sys.exit(0)

    mag_tag = mag_to_str(mag)

    print(f"\n[INFO] ── Image info ──────────────────────────────")
    print(f"[INFO]   File         : {os.path.basename(abs_image_path)}")
    print(f"[INFO]   Magnification: {mag_tag}")
    print(f"[INFO]   Scale bar    : {SCALEBAR_UM_LABEL[mag]} µm  "
          f"(check this matches the image)")
    print(f"[INFO]   px / µm      : {PX_PER_UM[mag]}")
    print(f"[INFO]   Method       : {method}")
    print(f"[INFO] ───────────────────────────────────────────\n")

    try:
        cast_letter, intermediate, sample_name = derive_relative_parts(
            abs_image_path, BASE_PATH
        )
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print(f"[INFO]   Cast         : {cast_letter} → {CAST_MAP.get(cast_letter, '?')}")
    print(f"[INFO]   Intermediate : {intermediate}")
    print(f"[INFO]   Sample       : {sample_name}\n")

    results_base = DEMO_RESULTS_BASE if demo_mode else RESULTS_BASE
    output_dir = derive_output_dir(cast_letter, intermediate, sample_name, results_base)
    if demo_mode:
        os.makedirs(output_dir, exist_ok=True)
    repeat_num = next_repeat_number(output_dir, sample_name, method, mag_tag)

    print(f"[INFO]   Repeat       : r{repeat_num}")
    if method == "linear" and repeat_num > 1:
        delta_frac = (repeat_num - 1) / 5.0
        print(f"[INFO]   Grid offset  : {delta_frac:.1f} × line_spacing "
              f"(cyclic/periodic)")
    print()

    tool = GrainInterceptTool(
        abs_image_path=abs_image_path,
        mag=mag,
        sample_name=sample_name,
        cast_letter=cast_letter,
        intermediate=intermediate,
        method=method,
        repeat_num=repeat_num,
        demo=demo_mode,
    )
    tool.run()
