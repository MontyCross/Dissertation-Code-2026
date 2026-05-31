"""
lom_analyse.py  —  Stereological analysis of scored LOM point-count data
=========================================================================
Masters thesis: Divorced Pearlite (DP) area fraction measurement

Usage:
    python lom_analyse.py
    A file dialog opens — navigate to the grid_scored_<SAMPLE>_<MAG>_r<N>.csv
    file and select it.  All outputs are written to the same folder.

Outputs (same folder as the selected CSV):
    lom_analysis_<SAMPLE>_<MAG>_r<N>.csv   — per-repeat Vv result
    lom_analysis_<SAMPLE>_<MAG>_r<N>.png   — diagnostic figure (hit map + summary)

Uncertainty strategy:
    This script computes only Vv = P_P / P_T for the single scored repeat.
    Cast-level uncertainty (SD across repeat sessions of a representative
    image) is assembled and applied by lom_dashboard.py, which owns the
    logic for deciding which sample is the uncertainty representative for
    each cast type.

Method:
    Vv = P_P / P_T  (ASTM E562 point fraction, excluding masked points)

File naming convention:
    Cast:      G=GC, H=HPDC, D=DCC
    Condition: AR=as-received, S=solutionised
               A=150°C, B=175°C, C=200°C
    Time:      4, 19, 43, 67, 100 hrs
    Code:      [Cast][Condition][Time]  e.g. HB19 = HPDC 175°C 19hrs
"""

import os

# ── PARAMETERS ────────────────────────────────────────────────────────────────
# ---INSTRUCTIONS ---
# Please set BASE_DIR to the folder where you extracted the Magnesium Masters Project data.
BASE_DIR = r"C:\Path\To\Project"

RESULTS_BASE      = os.path.join(BASE_DIR, "RESULTS")
PX_PER_UM_DEFAULT = 2.09   # fallback for legacy CSVs without px_per_um column
# ──────────────────────────────────────────────────────────────────────────────

import sys
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import tkinter as tk
from tkinter import filedialog


def pick_csv(initial_dir):
    """Open a file dialog to select a scored CSV. Returns path or None."""
    root = tk.Tk()
    root.withdraw()
    root.call("wm", "attributes", ".", "-topmost", True)
    path = filedialog.askopenfilename(
        title="Select scored CSV (grid_scored_*_r*.csv)",
        initialdir=initial_dir if os.path.isdir(initial_dir) else os.path.expanduser("~"),
        filetypes=[
            ("Scored CSV files", "grid_scored_*.csv"),
            ("CSV files",        "*.csv"),
            ("All files",        "*.*"),
        ],
    )
    root.destroy()
    return path if path else None


def sample_name_from_csv(csv_path):
    """
    Extract sample name, mag tag, and repeat number from the scored CSV filename.

    Handles both new-style and legacy filenames:
        grid_scored_DC19_10x_r2.csv  ->  ('DC19', '10x', 2)
        grid_scored_DC19_r2.csv      ->  ('DC19', None,  2)   <- legacy, no mag tag
        grid_scored_DC19.csv         ->  ('DC19', None,  None)
    """
    stem = os.path.splitext(os.path.basename(csv_path))[0]

    # New-style: grid_scored_<SAMPLE>_<MAG>_r<N>
    m = re.match(
        r"^grid_scored_(.+?)_((?:\d+(?:\.\d+)?)x)_r(\d+)$",
        stem, re.IGNORECASE,
    )
    if m:
        return m.group(1), m.group(2).lower(), int(m.group(3))

    # Legacy: grid_scored_<SAMPLE>_r<N>
    m = re.match(r"^grid_scored_(.+)_r(\d+)$", stem, re.IGNORECASE)
    if m:
        return m.group(1), None, int(m.group(2))

    # Older legacy: grid_scored_<SAMPLE>
    if stem.startswith("grid_scored_"):
        return stem[len("grid_scored_"):], None, None

    return stem, None, None


def cast_key_from_sample(sample_name):
    """
    Infer the cast key ('GC', 'HPDC', 'DCC') from the first letter of the
    sample code.  Returns None if the letter is unrecognised.
    """
    letter_map = {"G": "GC", "H": "HPDC", "D": "DCC"}
    if sample_name:
        return letter_map.get(sample_name[0].upper())
    return None


# ── 1. LOAD DATA ──────────────────────────────────────────────────────────────
def load_data(path):
    df = pd.read_csv(path)
    required = {"x", "y", "hit"}
    if not required.issubset(df.columns):
        raise ValueError(f"CSV must contain columns: {required}")

    if "px_per_um" in df.columns:
        px_per_um = float(df["px_per_um"].iloc[0])
        print(f"[INFO] px_per_um read from CSV: {px_per_um}")
    else:
        px_per_um = PX_PER_UM_DEFAULT
        print(f"[INFO] px_per_um column absent — using default {px_per_um} (legacy 10x file)")

    n_total_raw = len(df)
    df = df[df["hit"] != -1].copy()
    df["hit"] = df["hit"].astype(int)
    n_excluded = n_total_raw - len(df)
    print(f"[INFO] Loaded {n_total_raw} points; {n_excluded} excluded -> {len(df)} active")
    return df, px_per_um


# ── 2. Vv ─────────────────────────────────────────────────────────────────────
def compute_vv(df):
    P_P = int(df["hit"].sum())
    P_T = len(df)
    Vv  = P_P / P_T
    return Vv, P_P, P_T


# ── 3. DIAGNOSTIC FIGURE ──────────────────────────────────────────────────────
def make_figure(df, sample_name, repeat_num, Vv, P_P, P_T, output_path):
    """Two-panel figure: hit map (A) and results summary (B)."""

    fig = plt.figure(figsize=(12, 5))
    fig.patch.set_facecolor("#1a1a1a")
    gs  = gridspec.GridSpec(1, 2, figure=fig, wspace=0.32,
                            left=0.04, right=0.98, top=0.92, bottom=0.08)

    spine_col = "#555"
    title_kw  = dict(color="#90CAF9", fontsize=10, fontweight="bold", pad=6)

    def style_ax(ax, title):
        ax.set_facecolor("#2a2a2a")
        for sp in ax.spines.values():
            sp.set_color(spine_col)
        ax.tick_params(colors="white", labelsize=8)
        ax.xaxis.label.set_color("white")
        ax.yaxis.label.set_color("white")
        ax.set_title(title, **title_kw)

    # ── Panel A: hit map ──────────────────────────────────────────────────────
    ax_a = fig.add_subplot(gs[0, 0])
    style_ax(ax_a, "A  —  Hit Map")
    col_map = np.where(df["hit"] == 1, 0, 1).astype(float)
    sc = ax_a.scatter(df["x"], df["y"], c=col_map, cmap="RdYlGn",
                      vmin=0, vmax=1, s=6, linewidths=0)
    ax_a.set_aspect("equal")
    ax_a.invert_yaxis()
    ax_a.set_xlabel("x (px)", color="white")
    ax_a.set_ylabel("y (px)", color="white")
    cbar = fig.colorbar(sc, ax=ax_a, ticks=[0, 1], fraction=0.03, pad=0.02)
    cbar.ax.set_yticklabels(["DP", "Not-DP"], color="white", fontsize=7)
    cbar.outline.set_edgecolor(spine_col)

    # ── Panel B: results summary ──────────────────────────────────────────────
    ax_b = fig.add_subplot(gs[0, 1])
    style_ax(ax_b, "B  —  Results Summary")
    ax_b.axis("off")

    rows = [
        ("Sample",            sample_name),
        ("Repeat",            str(repeat_num) if repeat_num is not None else "—"),
        ("Total points  P_T", f"{P_T}"),
        ("DP hits  P_P",      f"{P_P}"),
        ("Not-DP",            f"{P_T - P_P}"),
        ("Vv = P_P / P_T",    f"{Vv:.4f}"),
        ("Uncertainty",       "assembled by dashboard"),
        ("",                  "from cast repeat sessions"),
    ]
    for row_i, (label, value) in enumerate(rows):
        y         = 0.93 - row_i * 0.115
        fc        = "#263238" if row_i % 2 == 0 else "#1a2428"
        highlight = row_i == 5
        ax_b.add_patch(plt.Rectangle(
            (0, y - 0.055), 1, 0.11,
            transform=ax_b.transAxes,
            color="#1B5E20" if highlight else fc,
            zorder=0, clip_on=False,
        ))
        ax_b.text(0.03, y, label, transform=ax_b.transAxes,
                  color="#B0BEC5", fontsize=8.5, va="center", family="monospace")
        ax_b.text(0.52, y, value, transform=ax_b.transAxes,
                  color="white", fontsize=9 if highlight else 8.5,
                  va="center", family="monospace",
                  fontweight="bold" if highlight else "normal")

    title_str = (
        f"LOM Analysis  —  {sample_name}  r{repeat_num}  |  Vv = {Vv:.4f}"
        if repeat_num is not None else
        f"LOM Analysis  —  {sample_name}  |  Vv = {Vv:.4f}"
    )
    fig.suptitle(title_str, color="white", fontsize=10, y=0.99)

    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"[INFO] Figure saved -> {output_path}")
    return fig


# ── 4. SAVE RESULTS CSV ───────────────────────────────────────────────────────
def save_results(sample_name, repeat_num, scored_at, Vv, P_P, P_T, path):
    """
    Save per-repeat result.  Uncertainty is assembled at the cast level by
    lom_dashboard.py — it is not computed here.
    """
    pd.DataFrame({
        "sample":    [sample_name],
        "repeat":    [repeat_num],
        "scored_at": [scored_at],
        "P_T":       [P_T],
        "P_P":       [P_P],
        "Vv":        [round(Vv, 6)],
    }).to_csv(path, index=False)
    print(f"[INFO] Results saved -> {path}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    demo_mode = "--demo" in sys.argv
    if demo_mode:
        sys.argv.remove("--demo")
        print("[DEMO] Running in demo mode — outputs go to temp directory.")

    # 1. CSV path — passed directly by lom_score.py, or chosen via file dialog
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        if not os.path.isfile(csv_path):
            print(f"[ERROR] Passed CSV not found: {csv_path}")
            sys.exit(1)
        print(f"[INFO] CSV passed from scorer: {csv_path}")
    else:
        csv_path = pick_csv(RESULTS_BASE)
        if csv_path is None:
            print("[INFO] No file selected — exiting.")
            sys.exit(0)

    # 2. Parse sample name, mag tag, and repeat number from the CSV filename
    sample_name, mag_tag, repeat_num = sample_name_from_csv(csv_path)
    sample_dir = os.path.dirname(csv_path)
    cast_key   = cast_key_from_sample(sample_name)

    try:
        _meta     = pd.read_csv(csv_path, nrows=1)
        scored_at = _meta["scored_at"].iloc[0] if "scored_at" in _meta.columns else "unknown"
    except Exception:
        scored_at = "unknown"

    # ── Demo mode: redirect outputs to temp directory ─────────────────────
    if demo_mode:
        import tempfile
        sample_dir = os.path.join(tempfile.gettempdir(), "msuite_demo",
                                  "RESULTS_ANALYSIS")
        os.makedirs(sample_dir, exist_ok=True)
        print(f"[DEMO] Output dir → {sample_dir}")

    mag_part   = f"_{mag_tag}" if mag_tag else ""
    repeat_tag = f"_r{repeat_num}" if repeat_num is not None else ""
    fig_path   = os.path.join(sample_dir,
                              f"lom_analysis_{sample_name}{mag_part}{repeat_tag}.png")
    out_csv    = os.path.join(sample_dir,
                              f"lom_analysis_{sample_name}{mag_part}{repeat_tag}.csv")

    print("=" * 60)
    print(f"  LOM Analysis  |  {sample_name}  {mag_tag or '(no mag tag)'}  r{repeat_num}")
    print(f"  Scored       : {scored_at}")
    print(f"  Cast key     : {cast_key or 'unrecognised'}")
    print(f"  Input        : {csv_path}")
    print(f"  Output       : {sample_dir}")
    print("=" * 60)

    # 3. Load and compute Vv
    df, px_per_um = load_data(csv_path)
    Vv, P_P, P_T  = compute_vv(df)
    print(f"  Vv  = {Vv:.4f}   (P_P={P_P}, P_T={P_T})")
    print(f"\n  Uncertainty will be assembled by lom_dashboard.py")
    print(f"  from repeat sessions of the cast representative image.\n")

    # 4. Save per-repeat result CSV
    save_results(sample_name, repeat_num, scored_at, Vv, P_P, P_T, out_csv)

    # 5. Figure
    make_figure(df, sample_name, repeat_num, Vv, P_P, P_T, fig_path)

    print("=" * 60)
    plt.show()
