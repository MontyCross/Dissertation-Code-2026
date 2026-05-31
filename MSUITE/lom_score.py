"""
lom_score.py  —  Interactive point-counting tool for LOM images
================================================================
Masters thesis: Divorced Pearlite (DP) area fraction measurement

Usage:
    python lom_score.py
    A file dialog opens — navigate to the LOM image and select it.
    Magnification is read from the filename (e.g. "10x af.png").
    If not found, the user is prompted and the file is renamed on disk.

Controls:
    Left-click               → toggle point as DP hit (green)
    Right-click              → clear point back to unscored
    E key                    → toggle nearest point as excluded (yellow)
    P key                    → toggle pan mode on/off (left-click drag to pan)
    Scroll wheel             → zoom in / out (centred on cursor)
    R key                    → reset zoom to full image
    T key                    → toggle red centre dots on/off (intersection reference)
    O key                    → toggle unscored outline colour: orange ↔ blue
    Close window             → no file saved (use Save & Analyse button)

Output CSV columns: x, y, hit, mag, px_per_um, repeat, scored_at, grid_offset_x,
                    grid_offset_y, grid_rotation_deg
    hit = 1 (DP), 0 (not-DP), -1 (excluded/ambiguous)

Repeat grid strategy:
    Repeat 1 (r1) : default grid — no offset, no rotation.
    Repeats 2-5   : rotation + translation.
                    Rotation   : θ = (r-1) * 9°  (9°, 18°, 27°, 36°) about
                                 the image centre.
                    Translation: Δx = (r-1)/5 * step_x,
                                 Δy = (r-1)/5 * step_y,
                                 applied in image coordinates after rotation.
                    Grid spacing is identical to r1 in both cases.  For
                    rotated grids the generation domain is extended to a
                    square of side 2 × half-diagonal so the rotated grid
                    always fully covers the image; points outside [0,W]×[0,H]
                    are then simply dropped.

File naming convention:
    Cast:      G=GC, H=HPDC, D=DCC
    Condition: AR=as-received, S=solutionised
               A=150°C, B=175°C, C=200°C
    Time:      4, 19, 43, 67, 100 hrs
    Code:      [Cast][Condition][Time]  e.g. HB19 = HPDC 175°C 19hrs

Image folder structure (under BASE_PATH):
    <CastLetter>/<IntermediateGroup>/<SampleCode>/<file>
    e.g.  D/DC/DC19/10x af.png

Output folder structure (under RESULTS_BASE) mirrors image source tree:
    DCC/DC/DC19/grid_scored_DC19_10x_r1.csv
    HPDC/HB/HB19/grid_scored_HB19_10x_r1.csv
    GC/GA/GAR/grid_scored_GAR_10x_r1.csv
    etc.
"""

import os

# ── PARAMETERS ────────────────────────────────────────────────────────────────
# ---INSTRUCTIONS ---
# Please set BASE_DIR to the folder where you extracted the Magnesium Masters Project data.
BASE_DIR = r"C:\Path\To\Project"

BASE_PATH    = os.path.join(BASE_DIR, "ANALYSED", "Etched")
RESULTS_BASE = os.path.join(BASE_DIR, "RESULTS")
N_TARGET     = 400
ZOOM_FACTOR  = 1.25                # per scroll-wheel tick

# Rotation step per repeat (degrees).  Repeat r gets θ = (r-1) * ROTATION_STEP_DEG
ROTATION_STEP_DEG = 9.0

# Pixel-to-micrometre ratios keyed by magnification
PX_PER_UM = {
     2.5:  0.522,
     5.0:  1.045,
    10.0:  2.09,
    20.0:  4.18,
    50.0: 10.45,
   100.0: 20.9,
}

# Scale-bar exclusion: top-left corner (sb_x, sb_y) of the excluded region.
# Everything with x >= sb_x AND y >= sb_y is masked (bottom-right corner).
SCALEBAR_ORIGIN = {
     2.5: (2805, 2000),
     5.0: (2857, 2000),
    10.0: (2857, 2000),
    20.0: (2857, 2000),
    50.0: (2857, 2000),
   100.0: (2857, 2000),
}

# Scale-bar physical length label (µm) — shown in the info strip for verification
SCALEBAR_UM_LABEL = {
     2.5: 500,
     5.0: 200,
    10.0: 100,
    20.0:  50,
    50.0:  20,
   100.0:  10,
}

# Magnification detection — checked longest-first to avoid "5x" matching inside "50x"
MAG_ORDER = [100.0, 50.0, 20.0, 10.0, 5.0, 2.5]
MAG_PATTERNS = {
    100.0: __import__("re").compile(r"100x",         __import__("re").IGNORECASE),
     50.0: __import__("re").compile(r"50x",          __import__("re").IGNORECASE),
     20.0: __import__("re").compile(r"20x",          __import__("re").IGNORECASE),
     10.0: __import__("re").compile(r"10x",          __import__("re").IGNORECASE),
      5.0: __import__("re").compile(r"(?<![.\d])5x", __import__("re").IGNORECASE),
      2.5: __import__("re").compile(r"2\.5x",        __import__("re").IGNORECASE),
}

# Marker radius: fixed in pixels so it does not scale with magnification.
MARKER_RADIUS_PX = 6
DOT_RADIUS_PX    = 1      # red centre-dot radius (data px) — kept small, opacity low
# ──────────────────────────────────────────────────────────────────────────────

import sys
import os
import re
import math
import numpy as np
import pandas as pd
import matplotlib
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
DEMO_RESULTS_BASE = os.path.join(tempfile.gettempdir(), "msuite_demo", "RESULTS")


# ── CAST-LETTER → FULL NAME MAP ───────────────────────────────────────────────
CAST_MAP = {"G": "GC", "H": "HPDC", "D": "DCC"}

# ── COLOUR CONSTANTS ──────────────────────────────────────────────────────────
COL_DEFAULT     = "#FF6600"   # orange — unscored outline
COL_DEFAULT_ALT = "#2196F3"   # blue   — unscored outline (O-key toggle)
COL_HIT         = "#4CAF50"   # green  — DP hit
COL_AMBIGUOUS   = "#FFC107"   # amber  — excluded
COL_DOT         = "#FF1744"   # red    — centre reference dot


# ── MAGNIFICATION HELPERS ─────────────────────────────────────────────────────

def mag_to_str(mag):
    """Return the canonical filename tag for a magnification: 2.5 → '2.5x', 10.0 → '10x'."""
    if mag == 2.5:
        return "2.5x"
    return f"{mag:g}x"


def parse_magnification(filepath):
    """Return magnification as float, or None if not found in filename."""
    name = os.path.basename(filepath)
    for mag in MAG_ORDER:
        if MAG_PATTERNS[mag].search(name):
            return mag
    return None


def prompt_magnification_and_rename(abs_path):
    """
    Prompt the user to enter the magnification, rename the file on disk
    to include it, and return (new_path, mag).  Returns (None, None) on cancel.
    """
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
        root2 = tk.Tk()
        root2.withdraw()
        messagebox.showerror(
            "Invalid entry",
            f"'{mag_str}' not recognised.\nValid: {', '.join(valid_str)}",
        )
        root2.destroy()
        return None, None

    mag       = lookup[mag_str]
    directory = os.path.dirname(abs_path)
    old_name  = os.path.basename(abs_path)
    new_name  = f"{mag_str} {old_name}"
    new_path  = os.path.join(directory, new_name)
    os.rename(abs_path, new_path)
    print(f"[INFO] Renamed '{old_name}' → '{new_name}'")
    return new_path, mag


# ── FILE / PATH HELPERS ───────────────────────────────────────────────────────

def pick_image(initial_dir):
    root = tk.Tk()
    root.withdraw()
    root.call("wm", "attributes", ".", "-topmost", True)
    path = filedialog.askopenfilename(
        title="Select LOM image",
        initialdir=initial_dir if os.path.isdir(initial_dir) else os.path.expanduser("~"),
        filetypes=[
            ("Image files", "*.png *.tif *.tiff *.jpg *.jpeg *.bmp"),
            ("All files",   "*.*"),
        ],
    )
    root.destroy()
    return path if path else None


def derive_relative_parts(abs_image_path, base_path):
    abs_img  = os.path.normcase(os.path.abspath(abs_image_path))
    abs_base = os.path.normcase(os.path.abspath(base_path))
    if not abs_img.startswith(abs_base):
        raise ValueError(
            f"Selected image is not inside BASE_PATH.\n"
            f"  Image : {abs_image_path}\n"
            f"  Base  : {base_path}"
        )
    rel   = os.path.relpath(abs_img, abs_base)
    parts = rel.split(os.sep)
    if len(parts) < 4:
        raise ValueError(
            f"Expected path depth <Cast>/<Intermediate>/<Sample>/<file> "
            f"but got: {rel}"
        )
    return parts[0].upper(), parts[1].upper(), parts[2].upper()


def derive_output_dir(cast_letter, intermediate, sample_name, results_base):
    cast_full = CAST_MAP.get(cast_letter, cast_letter)
    out_dir   = os.path.join(results_base, cast_full, intermediate, sample_name)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def next_repeat_number(output_dir, sample_name, mag_tag):
    pattern = re.compile(
        rf"^grid_scored_{re.escape(sample_name)}_{re.escape(mag_tag)}_r(\d+)\.csv$",
        re.IGNORECASE,
    )
    existing = []
    for f in os.listdir(output_dir):
        m = pattern.match(f)
        if m:
            existing.append(int(m.group(1)))
    return max(existing) + 1 if existing else 1


def load_image(path):
    try:
        img = Image.open(path)
        return np.array(img)
    except FileNotFoundError:
        print(f"[ERROR] Image not found: {path}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  GRID CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_scalebar_mask(xs, ys, sb_x, sb_y):
    """Return boolean mask: True where point is inside scale-bar exclusion zone."""
    return (xs >= sb_x) & (ys >= sb_y)


def _clip_to_image(xs, ys, img_w, img_h):
    """Return boolean mask: True where point is within image bounds."""
    return (xs >= 0) & (xs < img_w) & (ys >= 0) & (ys < img_h)


def build_default_grid(img_w, img_h, n_target):
    """
    Build the standard (repeat 1) grid: evenly spaced, no offset, no rotation.
    Returns (xs, ys, nx, ny, step_x, step_y).
    """
    aspect = img_w / img_h
    ny = int(round((n_target / aspect) ** 0.5))
    nx = int(round(ny * aspect))
    nx = max(nx, 2)
    ny = max(ny, 2)
    xs = np.linspace(img_w / (2 * nx), img_w - img_w / (2 * nx), nx)
    ys = np.linspace(img_h / (2 * ny), img_h - img_h / (2 * ny), ny)
    gx, gy = np.meshgrid(xs, ys)
    step_x = img_w / nx
    step_y = img_h / ny
    return gx.ravel(), gy.ravel(), nx, ny, step_x, step_y


def build_repeat_grid(img_w, img_h, sb_x, sb_y, repeat_num, n_target=N_TARGET):
    """
    Build an offset + rotated grid for repeat_num >= 2.

    Strategy
    --------
    1. Compute grid spacing from image dimensions (identical to r1).
    2. Build an oversized grid centred on the image centre, with domain
       extended to a square of side 2 × half-diagonal.  This guarantees
       full image coverage at any rotation angle.
    3. Rotate all points about the image centre by θ = (r-1) × 9°.
    4. Clip to image bounds [0, img_w) × [0, img_h).
    5. Apply translation offset in image coordinates:
           Δx = (r-1)/5 × step_x,  Δy = (r-1)/5 × step_y
    6. Re-clip to image bounds (offset may push edge points out).
    7. Apply scale-bar mask.

    Returns
    -------
    xs, ys          : surviving point coordinates
    nx, ny          : grid dimensions of the oversized pre-rotation grid
    offset_x/y      : translation applied (px)
    rotation_deg    : rotation applied (degrees)
    n_active        : number of active (non-scale-bar) points
    in_scalebar     : boolean mask (True = excluded)
    """
    r = repeat_num

    # ── grid spacing from image dimensions (same as r1) ────────────────────
    aspect = img_w / img_h
    ny0    = int(round((n_target / aspect) ** 0.5))
    nx0    = int(round(ny0 * aspect))
    nx0    = max(nx0, 2)
    ny0    = max(ny0, 2)
    step_x = img_w / nx0
    step_y = img_h / ny0

    # ── translation offset (applied after rotation) ────────────────────────
    offset_x = ((r - 1) / 5.0) * step_x
    offset_y = ((r - 1) / 5.0) * step_y

    # ── rotation ───────────────────────────────────────────────────────────
    theta_deg = (r - 1) * ROTATION_STEP_DEG
    theta_rad = math.radians(theta_deg)
    cos_t     = math.cos(theta_rad)
    sin_t     = math.sin(theta_rad)
    cx        = img_w / 2.0
    cy        = img_h / 2.0

    # ── oversized generation domain ────────────────────────────────────────
    # Half-diagonal of the image — the furthest any image pixel can be from
    # the centre.  A square domain of ±half_diag in each direction centred
    # on (cx, cy) guarantees full image coverage after any rotation.
    half_diag = math.hypot(cx, cy)

    # Number of grid points needed to span ±half_diag at the r1 spacing.
    # We use ceil to ensure we always cover the full extent.
    nx_big = math.ceil(2 * half_diag / step_x) + 2   # +2 for safety margin
    ny_big = math.ceil(2 * half_diag / step_y) + 2

    # Generate oversized grid, centred on image centre
    # Points run from  cx - (nx_big/2)*step_x  to  cx + (nx_big/2)*step_x
    x_start = cx - (nx_big / 2.0) * step_x + step_x / 2.0
    y_start = cy - (ny_big / 2.0) * step_y + step_y / 2.0
    xs_base = x_start + np.arange(nx_big) * step_x
    ys_base = y_start + np.arange(ny_big) * step_y
    gx, gy  = np.meshgrid(xs_base, ys_base)
    xs_flat = gx.ravel()
    ys_flat = gy.ravel()

    # ── step 3: rotate about image centre ─────────────────────────────────
    dx = xs_flat - cx
    dy = ys_flat - cy
    xs_rot = cx + cos_t * dx - sin_t * dy
    ys_rot = cy + sin_t * dx + cos_t * dy

    # ── step 4: clip to image bounds ──────────────────────────────────────
    in_bounds = _clip_to_image(xs_rot, ys_rot, img_w, img_h)
    xs_rot    = xs_rot[in_bounds]
    ys_rot    = ys_rot[in_bounds]

    # ── step 5: apply translation offset ──────────────────────────────────
    xs_rot = xs_rot + offset_x
    ys_rot = ys_rot + offset_y

    # ── step 6: re-clip after offset ──────────────────────────────────────
    in_bounds2 = _clip_to_image(xs_rot, ys_rot, img_w, img_h)
    xs_rot     = xs_rot[in_bounds2]
    ys_rot     = ys_rot[in_bounds2]

    # ── step 7: scale-bar mask ────────────────────────────────────────────
    sb_mask  = _apply_scalebar_mask(xs_rot, ys_rot, sb_x, sb_y)
    n_active = int((~sb_mask).sum())

    print(f"[INFO] Repeat {r}: oversized grid {nx_big}×{ny_big}, "
          f"θ={theta_deg:.0f}°, "
          f"offset=({offset_x:.1f},{offset_y:.1f})px, "
          f"total={len(xs_rot)}, active={n_active}")

    return (xs_rot, ys_rot, nx_big, ny_big,
            offset_x, offset_y, theta_deg,
            n_active, sb_mask)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCORER
# ═══════════════════════════════════════════════════════════════════════════════

class Scorer:
    def __init__(self, abs_image_path, mag, sample_name, cast_letter,
                 intermediate, repeat_num, demo=False):
        self.abs_image_path = abs_image_path
        self.mag            = mag
        self.sample_name    = sample_name
        self.cast_letter    = cast_letter
        self.intermediate   = intermediate
        self.repeat_num     = repeat_num
        self.output_path    = None
        self.scored_at      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.demo           = demo

        self.px_per_um = PX_PER_UM[mag]
        self.sb_origin = SCALEBAR_ORIGIN[mag]
        self.sb_label  = SCALEBAR_UM_LABEL[mag]

        self.img = load_image(abs_image_path)
        self.h, self.w = self.img.shape[:2]

        sb_x, sb_y = self.sb_origin

        # ── build grid depending on repeat number ──────────────────────────
        if repeat_num == 1:
            xs, ys, self.nx, self.ny, _, _ = build_default_grid(
                self.w, self.h, N_TARGET)
            self.grid_offset_x = 0.0
            self.grid_offset_y = 0.0
            self.grid_rotation = 0.0
            in_scalebar        = _apply_scalebar_mask(xs, ys, sb_x, sb_y)
        else:
            (xs, ys, self.nx, self.ny,
             self.grid_offset_x, self.grid_offset_y, self.grid_rotation,
             n_active, in_scalebar) = build_repeat_grid(
                self.w, self.h, sb_x, sb_y, repeat_num, N_TARGET
            )

        self.xs   = xs
        self.ys   = ys
        self.n    = len(xs)
        self.hits = np.zeros(self.n, dtype=int)
        self.hits[in_scalebar] = -1

        n_masked = int(in_scalebar.sum())
        n_active = int((~in_scalebar).sum())
        print(f"[INFO] Grid: {self.nx}×{self.ny} → {self.n} total points  |  "
              f"{n_masked} scale-bar masked  |  {n_active} active")
        if repeat_num > 1:
            print(f"[INFO] Repeat {repeat_num}: offset=({self.grid_offset_x:.1f},"
                  f"{self.grid_offset_y:.1f}) px  |  "
                  f"rotation={self.grid_rotation:.0f}°")

        # Pan / toggle state
        self._pan_mode     = False
        self._pan_active   = False
        self._pan_start    = None
        self._xlim_start   = None
        self._ylim_start   = None
        self._dots_visible = False
        self._outline_alt  = False

        print(f"[INFO] Sample       : {self.sample_name}  (repeat {self.repeat_num})")
        print(f"[INFO] Magnification: {self.mag:g}x  |  "
              f"{self.px_per_um} px/µm  |  "
              f"Scale bar label: {self.sb_label} µm")

        self._build_figure()

    # ── current unscored outline colour ───────────────────────────────────────
    @property
    def _col_default(self):
        return COL_DEFAULT_ALT if self._outline_alt else COL_DEFAULT

    # ── Figure ────────────────────────────────────────────────────────────────
    def _build_figure(self):
        self.fig = plt.figure(figsize=(16, 10))
        self.fig.patch.set_facecolor("#1a1a1a")

        try:
            self.fig.canvas.toolbar.pack_forget()
        except Exception:
            pass
        try:
            matplotlib.rcParams["toolbar"] = "None"
        except Exception:
            pass

        STRIP_IN   = 0.65
        STRIP_FRAC = STRIP_IN / self.fig.get_figheight()
        PAD_FRAC   = 0.004

        self.ax = self.fig.add_axes([0.0, STRIP_FRAC + PAD_FRAC, 1.0,
                                     1.0 - STRIP_FRAC - PAD_FRAC])
        self.ax.set_facecolor("#1a1a1a")
        self.ax.imshow(self.img, origin="upper", interpolation="nearest")
        self.ax.set_xlim(0, self.w)
        self.ax.set_ylim(self.h, 0)
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.axis("off")

        self._xlim_full = (0.0, float(self.w))
        self._ylim_full = (float(self.h), 0.0)

        # Shade scale-bar exclusion zone
        sb_x, sb_y = self.sb_origin
        self.ax.add_patch(mpatches.Rectangle(
            (sb_x, sb_y),
            self.w - sb_x, self.h - sb_y,
            linewidth=1, edgecolor="#FF6600",
            facecolor="#FF6600", alpha=0.18, zorder=2,
        ))

        # Grid circles
        self.circles = []
        for i in range(self.n):
            is_default = self.hits[i] == 0
            col = self._colour(i)
            c = plt.Circle(
                (self.xs[i], self.ys[i]),
                MARKER_RADIUS_PX,
                facecolor=(0, 0, 0, 0) if is_default else col,
                edgecolor=self._col_default if is_default else col,
                alpha=0.45,
                linewidth=0.8 if is_default else 0,
                zorder=3,
            )
            self.ax.add_patch(c)
            self.circles.append(c)

        # Red centre dots (hidden by default)
        self.dots = []
        for i in range(self.n):
            d = plt.Circle(
                (self.xs[i], self.ys[i]),
                DOT_RADIUS_PX,
                facecolor=COL_DOT,
                edgecolor="none",
                alpha=0.4,
                visible=False,
                zorder=5,
            )
            self.ax.add_patch(d)
            self.dots.append(d)

        # Control strip
        self.ax_strip = self.fig.add_axes([0.0, 0.0, 1.0, STRIP_FRAC])
        self.ax_strip.set_facecolor("#111111")
        self.ax_strip.axis("off")

        repeat_detail = (
            f"r{self.repeat_num}  |  "
            f"offset=({self.grid_offset_x:.1f},{self.grid_offset_y:.1f})px  |  "
            f"θ={self.grid_rotation:.0f}°"
        )
        info = (
            f"{self.sample_name}  |  {os.path.basename(self.abs_image_path)}  |  "
            f"Mag: {self.mag:g}x  |  Scale bar: {self.sb_label} µm  |  "
            f"{self.px_per_um} px/µm  |  Grid: total={self.n}, active={int(np.sum(self.hits == 0))}  |  "
            f"{repeat_detail}  |  "
            f"Scroll=zoom  P=pan  R=reset  T=dots  O=outline  E=exclude"
        )
        self.ax_strip.text(
            0.005, 0.97, info,
            transform=self.ax_strip.transAxes,
            color="#90CAF9", fontsize=7.5, va="top", family="monospace",
            clip_on=False,
        )

        self.pan_indicator = self.ax_strip.text(
            0.5, 0.55, "",
            transform=self.ax_strip.transAxes,
            color="#FFD600", fontsize=9, va="top", family="monospace",
            fontweight="bold", ha="center", clip_on=False,
        )

        self.status_text = self.ax_strip.text(
            0.005, 0.52, "",
            transform=self.ax_strip.transAxes,
            color="white", fontsize=8.5, va="top", family="monospace",
            clip_on=False,
        )
        self._update_status()

        legend_elements = [
            mpatches.Patch(facecolor=COL_DEFAULT,   label="Not-DP  [R-click]"),
            mpatches.Patch(facecolor=COL_HIT,       label="DP hit  [L-click]"),
            mpatches.Patch(facecolor=COL_AMBIGUOUS, label="Excluded  [E key]"),
            mpatches.Patch(facecolor=COL_DOT,       label="Centre dot  [T toggle]"),
        ]
        self.ax_strip.legend(
            handles=legend_elements,
            loc="lower left",
            bbox_to_anchor=(0.0, 0.0),
            ncol=4,
            fontsize=7.5,
            framealpha=0,
            labelcolor="white",
            handlelength=1.0,
            handleheight=0.6,
            handletextpad=0.4,
            borderpad=0.2,
            columnspacing=0.8,
            borderaxespad=0.2,
        )

        # Buttons
        BTN_H       = STRIP_FRAC * 0.82
        BTN_Y       = (STRIP_FRAC - BTN_H) / 2
        GAP         = 0.008
        RIGHT_EDGE  = 0.995
        BTN_W_SAVE  = 0.10
        BTN_W_RESET = 0.065
        BTN_W_VIEW  = 0.075

        ax_rst = self.fig.add_axes([
            RIGHT_EDGE - BTN_W_RESET,
            BTN_Y, BTN_W_RESET, BTN_H,
        ])
        self.btn_reset = Button(ax_rst, "Reset",
                                color="#B71C1C", hovercolor="#D32F2F")
        self.btn_reset.label.set_color("white")
        self.btn_reset.label.set_fontsize(8)
        self.btn_reset.on_clicked(self._on_reset)

        ax_view = self.fig.add_axes([
            RIGHT_EDGE - BTN_W_RESET - GAP - BTN_W_VIEW,
            BTN_Y, BTN_W_VIEW, BTN_H,
        ])
        self.btn_view = Button(ax_view, "Reset View  [R]",
                               color="#1A3A4A", hovercolor="#1F5070")
        self.btn_view.label.set_color("white")
        self.btn_view.label.set_fontsize(8)
        self.btn_view.on_clicked(lambda e: self._reset_view())

        ax_btn = self.fig.add_axes([
            RIGHT_EDGE - BTN_W_RESET - GAP - BTN_W_VIEW - GAP - BTN_W_SAVE,
            BTN_Y, BTN_W_SAVE, BTN_H,
        ])
        self.btn_save = Button(ax_btn, "Save & Analyse",
                               color="#37474F", hovercolor="#546E7A")
        self.btn_save.label.set_color("white")
        self.btn_save.label.set_fontsize(8)
        self.btn_save.on_clicked(self._on_save)

        canvas = self.fig.canvas
        canvas.mpl_connect("button_press_event",   self._on_press)
        canvas.mpl_connect("button_release_event", self._on_release)
        canvas.mpl_connect("motion_notify_event",  self._on_motion)
        canvas.mpl_connect("scroll_event",         self._on_scroll)
        canvas.mpl_connect("key_press_event",      self._on_key)
        canvas.mpl_connect("key_release_event",    self._on_key_release)
        canvas.mpl_connect("close_event",          self._on_close)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _colour(self, i):
        v = self.hits[i]
        if v ==  1: return COL_HIT
        if v == -1: return COL_AMBIGUOUS
        return self._col_default

    def _nearest(self, x, y):
        d2 = (self.xs - x) ** 2 + (self.ys - y) ** 2
        return int(np.argmin(d2))

    def _update_circle(self, i):
        col        = self._colour(i)
        is_default = self.hits[i] == 0
        self.circles[i].set_facecolor((0, 0, 0, 0) if is_default else col)
        self.circles[i].set_edgecolor(self._col_default if is_default else col)
        self.circles[i].set_linewidth(0.8 if is_default else 0)

    def _update_status(self):
        n_hit   = int(np.sum(self.hits == 1))
        n_excl  = int(np.sum(self.hits == -1))
        n_unsco = int(np.sum(self.hits == 0))
        denom   = self.n - n_excl
        vv_est  = n_hit / denom if denom > 0 else 0.0
        self.status_text.set_text(
            f"DP hits: {n_hit}   Not-DP: {n_unsco}   "
            f"Excluded: {n_excl}   "
            f"Vv (provisional) = {vv_est:.4f}"
        )

    def _reset_view(self):
        self.ax.set_xlim(self._xlim_full)
        self.ax.set_ylim(self._ylim_full)
        self.fig.canvas.draw_idle()

    # ── Toggles ───────────────────────────────────────────────────────────────
    def _toggle_dots(self):
        self._dots_visible = not self._dots_visible
        for d in self.dots:
            d.set_visible(self._dots_visible)
        self.fig.canvas.draw_idle()
        print(f"[INFO] Centre dots {'ON' if self._dots_visible else 'OFF'}")

    def _toggle_outline_colour(self):
        self._outline_alt = not self._outline_alt
        new_col = self._col_default
        for i, c in enumerate(self.circles):
            if self.hits[i] == 0:
                c.set_edgecolor(new_col)
        self.fig.canvas.draw_idle()
        print(f"[INFO] Unscored outline → {'BLUE' if self._outline_alt else 'ORANGE'}")

    def _toggle_exclude_nearest(self, xd, yd):
        idx = self._nearest(xd, yd)
        self.hits[idx] = 0 if self.hits[idx] == -1 else -1
        self._update_circle(idx)
        self._update_status()
        self.fig.canvas.draw_idle()

    def _toggle_pan_mode(self):
        self._pan_mode   = not self._pan_mode
        self._pan_active = False

        if self._pan_mode:
            self.pan_indicator.set_text("⬡  PAN MODE  —  drag to pan  |  P to exit")
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

    # ── Events ────────────────────────────────────────────────────────────────
    def _on_press(self, event):
        if event.inaxes != self.ax:
            return

        if event.button == 1:
            if self._pan_mode:
                self._pan_active = True
                self._pan_start  = (event.xdata, event.ydata)
                self._xlim_start = self.ax.get_xlim()
                self._ylim_start = self.ax.get_ylim()
            else:
                idx = self._nearest(event.xdata, event.ydata)
                self.hits[idx] = 0 if self.hits[idx] == 1 else 1
                self._update_circle(idx)
                self._update_status()
                self.fig.canvas.draw_idle()

        elif event.button == 3 and not self._pan_mode:
            idx = self._nearest(event.xdata, event.ydata)
            self.hits[idx] = 0
            self._update_circle(idx)
            self._update_status()
            self.fig.canvas.draw_idle()

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
        xdata, ydata = event.xdata, event.ydata
        if xdata is None or ydata is None:
            return
        factor = 1.0 / ZOOM_FACTOR if event.button == "up" else ZOOM_FACTOR
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        self.ax.set_xlim(xdata + (x0 - xdata) * factor,
                         xdata + (x1 - xdata) * factor)
        self.ax.set_ylim(ydata + (y0 - ydata) * factor,
                         ydata + (y1 - ydata) * factor)
        self.fig.canvas.draw_idle()

    def _on_key(self, event):
        key = event.key.lower() if event.key else ""

        if key == "r":
            self._reset_view()
        elif key == "p":
            self._toggle_pan_mode()
        elif key == "t":
            self._toggle_dots()
        elif key == "o":
            self._toggle_outline_colour()
        elif key == "e":
            if not self._pan_mode and event.inaxes == self.ax:
                xd, yd = self.ax.transData.inverted().transform(
                    (event.x, event.y)
                )
                self._toggle_exclude_nearest(xd, yd)

    def _on_key_release(self, event):
        pass

    def _on_close(self, event):
        pass

    # ── Save / Reset ──────────────────────────────────────────────────────────
    def _on_save(self, event=None):
        n_hit   = int(np.sum(self.hits == 1))
        n_excl  = int(np.sum(self.hits == -1))
        n_unsco = int(np.sum(self.hits == 0))
        denom   = self.n - n_excl
        vv      = n_hit / denom if denom > 0 else 0.0

        mag_tag = mag_to_str(self.mag)

        # ── Demo mode: write to temp dir, pass --demo to analyser ─────────
        if self.demo:
            demo_tag = "[DEMO] " 
            msg = (
                f"{demo_tag}Results will NOT be saved to disk.\n\n"
                f"Sample       :  {self.sample_name}  (repeat {self.repeat_num})\n"
                f"Magnification:  {self.mag:g}x\n"
                f"Scored       :  {self.scored_at}\n"
                f"Grid offset  :  ({self.grid_offset_x:.1f}, {self.grid_offset_y:.1f}) px\n"
                f"Rotation     :  {self.grid_rotation:.0f}°\n\n"
                f"DP hits      :  {n_hit}\n"
                f"Not-DP       :  {n_unsco}\n"
                f"Excluded     :  {n_excl}\n"
                f"Vv (est.)    :  {vv:.4f}\n\n"
                f"Run analysis on temporary data?"
            )
            root = tk.Tk()
            root.withdraw()
            root.call("wm", "attributes", ".", "-topmost", True)
            confirmed = messagebox.askyesno("Demo — Save & Analyse", msg, parent=root)
            root.destroy()

            if not confirmed:
                return

            tmp_dir = derive_output_dir(self.cast_letter, self.intermediate,
                                        self.sample_name, DEMO_RESULTS_BASE)
            self.output_path = os.path.join(
                tmp_dir,
                f"grid_scored_{self.sample_name}_{mag_tag}_r{self.repeat_num}.csv"
            )
            self._save_to_disk()
            print(f"[DEMO] Temp CSV → {self.output_path}")

            analyser_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "lom_analyse.py")
            subprocess.Popen([sys.executable, analyser_path,
                              self.output_path, "--demo"])
            plt.close(self.fig)
            return

        # ── Normal mode ───────────────────────────────────────────────────
        output_dir  = derive_output_dir(self.cast_letter, self.intermediate,
                                        self.sample_name, RESULTS_BASE)
        output_path = os.path.join(
            output_dir,
            f"grid_scored_{self.sample_name}_{mag_tag}_r{self.repeat_num}.csv"
        )

        msg = (
            f"Sample       :  {self.sample_name}  (repeat {self.repeat_num})\n"
            f"Magnification:  {self.mag:g}x\n"
            f"Scored       :  {self.scored_at}\n"
            f"Grid offset  :  ({self.grid_offset_x:.1f}, {self.grid_offset_y:.1f}) px\n"
            f"Rotation     :  {self.grid_rotation:.0f}°\n\n"
            f"DP hits      :  {n_hit}\n"
            f"Not-DP       :  {n_unsco}\n"
            f"Excluded     :  {n_excl}\n"
            f"Vv (est.)    :  {vv:.4f}\n\n"
            f"Save CSV and run analysis?"
        )
        root = tk.Tk()
        root.withdraw()
        root.call("wm", "attributes", ".", "-topmost", True)
        confirmed = messagebox.askyesno("Confirm Save & Analyse", msg, parent=root)
        root.destroy()

        if not confirmed:
            return

        self.output_path = output_path
        self._save_to_disk()
        analyser_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "lom_analyse.py")
        subprocess.Popen([sys.executable, analyser_path, self.output_path])
        plt.close(self.fig)

    def _save_to_disk(self):
        df = pd.DataFrame({
            "x":                  self.xs,
            "y":                  self.ys,
            "hit":                self.hits.copy(),
            "mag":                self.mag,
            "px_per_um":          self.px_per_um,
            "repeat":             self.repeat_num,
            "scored_at":          self.scored_at,
            "grid_offset_x":      self.grid_offset_x,
            "grid_offset_y":      self.grid_offset_y,
            "grid_rotation_deg":  self.grid_rotation,
        })
        df.to_csv(self.output_path, index=False)
        n_hit  = int(np.sum(self.hits == 1))
        n_excl = int(np.sum(self.hits == -1))
        denom  = len(df) - n_excl
        vv     = n_hit / denom if denom > 0 else 0.0
        print(f"[INFO] Saved {len(df)} points → {self.output_path}")
        print(f"       DP hits = {n_hit} / {denom} active points  →  Vv = {vv:.4f}")

    def _on_reset(self, event=None):
        sb_x, sb_y = self.sb_origin
        in_scalebar = _apply_scalebar_mask(self.xs, self.ys, sb_x, sb_y)
        self.hits[:] = 0
        self.hits[in_scalebar] = -1
        for i, c in enumerate(self.circles):
            if in_scalebar[i]:
                c.set_facecolor(COL_AMBIGUOUS)
                c.set_edgecolor(COL_AMBIGUOUS)
                c.set_linewidth(0)
            else:
                c.set_facecolor((0, 0, 0, 0))
                c.set_edgecolor(self._col_default)
                c.set_linewidth(0.8)
        self._update_status()
        self.fig.canvas.draw_idle()
        print("[INFO] All user scores reset (scale bar exclusions retained).")

    def run(self):
        plt.show()


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    demo_mode = "--demo" in sys.argv
    if demo_mode:
        sys.argv.remove("--demo")
        print("[DEMO] Running in demo mode — no data will be saved to results.")

    abs_image_path = pick_image(BASE_PATH)
    if abs_image_path is None:
        print("[INFO] No file selected — exiting.")
        sys.exit(0)

    # Detect magnification from filename; prompt + rename if missing
    mag = parse_magnification(abs_image_path)
    if mag is None:
        abs_image_path, mag = prompt_magnification_and_rename(abs_image_path)
        if abs_image_path is None or mag is None:
            print("[INFO] Magnification entry cancelled — exiting.")
            sys.exit(0)

    print(f"\n[INFO] ── Image info ──────────────────────────────────")
    print(f"[INFO]   File         : {os.path.basename(abs_image_path)}")
    print(f"[INFO]   Magnification: {mag:g}x")
    print(f"[INFO]   px / µm      : {PX_PER_UM[mag]}")
    print(f"[INFO]   Scale bar    : {SCALEBAR_UM_LABEL[mag]} µm  "
          f"(verify this matches the image)")
    print(f"[INFO]   SB origin    : {SCALEBAR_ORIGIN[mag]}")
    print(f"[INFO] ───────────────────────────────────────────────\n")

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

    # Determine repeat number from existing files in output dir
    results_base = DEMO_RESULTS_BASE if demo_mode else RESULTS_BASE
    output_dir = derive_output_dir(cast_letter, intermediate, sample_name, results_base)
    mag_tag    = mag_to_str(mag)
    repeat_num = next_repeat_number(output_dir, sample_name, mag_tag)

    print(f"[INFO]   Repeat number: {repeat_num}")
    if repeat_num > 1:
        print(f"[INFO]   Grid will use offset + {(repeat_num-1)*ROTATION_STEP_DEG:.0f}° rotation")
    print()

    scorer = Scorer(
        abs_image_path=abs_image_path,
        mag=mag,
        sample_name=sample_name,
        cast_letter=cast_letter,
        intermediate=intermediate,
        repeat_num=repeat_num,
        demo=demo_mode,
    )
    scorer.run()
