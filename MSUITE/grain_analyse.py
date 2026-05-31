"""
grain_analyse.py  —  Post-processor for grain intercept counting results
=========================================================================
Masters thesis: AZ91 / AZ80 magnesium alloy grain size analysis

Usage:
    python grain_analyse.py [path_to_summary_csv]

    If no path is supplied a file dialog opens in RESULTS_BASE.
    Can also be called programmatically from grain_intercept.py.

Method:
    Reads an intercept_linear_<sample>_<mag>_r<N>_summary.csv  OR
               intercept_circular_<sample>_<mag>_r<N>_summary.csv

    Computes mean N̄_L across all lines / circles (Heyn approach, all
    orientations combined as a single population per ASTM E112 §13.4):

        N̄_L  = total_intercept_count / total_length_mm   [mm⁻¹]

    Converts to ASTM grain size number G using Table 6 / Eq A1.6 of
    ASTM E112-25:

        G = 6.643856 × log₁₀(N̄_L) − 3.288    (N̄_L in mm⁻¹)

    Mean lineal intercept:
        l̄ = 1 / N̄_L   [mm]  →  also reported in µm

Output:
    grain_analysis_<sample>_<mag>_r<N>.csv  in the same folder as the
    input summary CSV.

    Columns:
        sample, magnification, mag_tag, method, repeat,
        n_features_used, total_intercept_count, total_length_um,
        total_length_mm, NL_per_mm, mean_intercept_um, G,
        scored_at, analysed_at
"""

import sys
import os
import re
import math
import pandas as pd
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox


# ── PARAMETERS ────────────────────────────────────────────────────────────────
# --- INSTRUCTIONS ---
# Please set BASE_DIR to the folder where you extracted the Magnesium Masters Project data.
BASE_DIR = r"C:\Path\To\Project"

RESULTS_BASE = os.path.join(BASE_DIR, "RESULTS_GRAIN_SIZE")
# ──────────────────────────────────────────────────────────────────────────────

def pick_csv(initial_dir=None):
    root = tk.Tk()
    root.withdraw()
    root.call("wm", "attributes", ".", "-topmost", True)
    start = initial_dir if (initial_dir and os.path.isdir(initial_dir)) \
            else os.path.expanduser("~")
    path = filedialog.askopenfilename(
        title="Select intercept summary CSV",
        initialdir=start,
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    root.destroy()
    return path if path else None


def compute_G(NL_per_mm):
    """
    ASTM E112-25 Table 6 / Annex A1 Eq A1.6:
        G = 6.643856 × log10(N̄_L) − 3.288
    N̄_L must be in mm⁻¹.
    Returns None if NL_per_mm <= 0.
    """
    if NL_per_mm <= 0:
        return None
    return 6.643856 * math.log10(NL_per_mm) - 3.288


def analyse(summary_csv_path):
    """
    Read a summary CSV, compute G, write grain_analysis CSV.
    Returns path to output CSV, or None on failure.
    """
    if not os.path.isfile(summary_csv_path):
        print(f"[ERROR] File not found: {summary_csv_path}")
        return None

    try:
        df = pd.read_csv(summary_csv_path)
    except Exception as e:
        print(f"[ERROR] Could not read CSV: {e}")
        return None

    required = {"total_count", "length_um", "NL_per_mm", "sample",
                "magnification", "method", "repeat"}
    # length_um / NL_per_mm present for linear; circumference_um / NL_per_mm for circular
    if "total_count" not in df.columns or "NL_per_mm" not in df.columns:
        print(f"[ERROR] CSV missing required columns. Found: {list(df.columns)}")
        return None

    # ── Determine length column ────────────────────────────────────────────
    method = str(df["method"].iloc[0]).strip().lower()
    if method == "linear":
        if "length_um" not in df.columns:
            print("[ERROR] Linear summary missing 'length_um' column.")
            return None
        length_col = "length_um"
    else:
        if "circumference_um" not in df.columns:
            print("[ERROR] Circular summary missing 'circumference_um' column.")
            return None
        length_col = "circumference_um"

    # ── Aggregate across all features ─────────────────────────────────────
    total_count_all  = float(df["total_count"].sum())
    total_length_um  = float(df[length_col].sum())
    total_length_mm  = total_length_um / 1000.0
    n_features       = len(df)

    if total_length_mm <= 0:
        print("[ERROR] Total line length is zero — nothing to analyse.")
        return None

    NL_per_mm       = total_count_all / total_length_mm
    G               = compute_G(NL_per_mm)
    mean_intercept_mm = 1.0 / NL_per_mm if NL_per_mm > 0 else None
    mean_intercept_um = mean_intercept_mm * 1000.0 if mean_intercept_mm else None

    # ── Metadata from summary ─────────────────────────────────────────────
    sample      = str(df["sample"].iloc[0])
    magnification = float(df["magnification"].iloc[0])
    mag_tag     = str(df["mag_tag"].iloc[0]) if "mag_tag" in df.columns else f"{magnification:g}x"
    repeat      = int(df["repeat"].iloc[0])
    scored_at   = str(df["scored_at"].iloc[0]) if "scored_at" in df.columns else ""
    analysed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = {
        "sample":                sample,
        "magnification":         magnification,
        "mag_tag":               mag_tag,
        "method":                method,
        "repeat":                repeat,
        "n_features_used":       n_features,
        "total_intercept_count": round(total_count_all, 2),
        "total_length_um":       round(total_length_um, 4),
        "total_length_mm":       round(total_length_mm, 6),
        "NL_per_mm":             round(NL_per_mm, 6),
        "mean_intercept_um":     round(mean_intercept_um, 4) if mean_intercept_um else None,
        "G":                     round(G, 4) if G is not None else None,
        "scored_at":             scored_at,
        "analysed_at":           analysed_at,
    }

    # ── Write output CSV ───────────────────────────────────────────────────
    out_dir  = os.path.dirname(summary_csv_path)
    out_name = f"grain_analysis_{sample}_{mag_tag}_r{repeat}.csv"
    out_path = os.path.join(out_dir, out_name)

    pd.DataFrame([result]).to_csv(out_path, index=False)

    print(f"\n[INFO] ── Grain size analysis ─────────────────────────────")
    print(f"[INFO]   Sample            : {sample}")
    print(f"[INFO]   Method            : {method}")
    print(f"[INFO]   Magnification     : {mag_tag}")
    print(f"[INFO]   Repeat            : r{repeat}")
    print(f"[INFO]   Features used     : {n_features}")
    print(f"[INFO]   Total count       : {total_count_all:.1f}")
    print(f"[INFO]   Total length      : {total_length_um:.1f} µm  "
          f"({total_length_mm:.4f} mm)")
    print(f"[INFO]   N̄_L               : {NL_per_mm:.4f} mm⁻¹")
    if mean_intercept_um:
        print(f"[INFO]   Mean intercept    : {mean_intercept_um:.2f} µm")
    if G is not None:
        print(f"[INFO]   ASTM G            : {G:.2f}")
    print(f"[INFO] ────────────────────────────────────────────────────")
    print(f"[INFO]   Output → {out_path}\n")

    return out_path


def main():
    demo_mode = "--demo" in sys.argv
    if demo_mode:
        sys.argv.remove("--demo")
        print("[DEMO] Running in demo mode — outputs go to temp directory.")

    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = pick_csv(RESULTS_BASE)

    if not csv_path:
        print("[INFO] No file selected — exiting.")
        sys.exit(0)

    # ── Demo standalone: redirect output to temp dir ──────────────────────
    if demo_mode and not csv_path.startswith(
            __import__("tempfile").gettempdir()):
        # Input CSV is from real results — copy it to temp so analyse()
        # writes output alongside the copy, not alongside the real data.
        import shutil, tempfile
        tmp_dir  = os.path.join(tempfile.gettempdir(), "msuite_demo",
                                "RESULTS_GRAIN_SIZE_ANALYSIS")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_csv  = os.path.join(tmp_dir, os.path.basename(csv_path))
        shutil.copy2(csv_path, tmp_csv)
        csv_path = tmp_csv
        print(f"[DEMO] Working copy → {tmp_csv}")

    out = analyse(csv_path)
    if out is None:
        sys.exit(1)

    # Brief GUI confirmation
    demo_tag = "[DEMO] " if demo_mode else ""
    root = tk.Tk(); root.withdraw()
    try:
        df = pd.read_csv(out)
        G  = df["G"].iloc[0]
        NL = df["NL_per_mm"].iloc[0]
        l  = df["mean_intercept_um"].iloc[0]
        save_line = (f"\n\n{demo_tag}Temp output:\n{out}" if demo_mode
                     else f"\n\nSaved to:\n{out}")
        messagebox.showinfo(
            f"{demo_tag}Analysis complete",
            f"Sample  :  {df['sample'].iloc[0]}  (r{df['repeat'].iloc[0]})\n"
            f"N̄_L     :  {NL:.4f} mm⁻¹\n"
            f"Mean ℓ̄  :  {l:.2f} µm\n"
            f"ASTM G  :  {G:.2f}"
            f"{save_line}",
            parent=root,
        )
    except Exception:
        pass
    root.destroy()


if __name__ == "__main__":
    main()
