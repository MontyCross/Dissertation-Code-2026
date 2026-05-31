"""
lom_dashboard.py  —  Interactive dashboard for DP area fraction results
=======================================================================
Masters thesis: Divorced Pearlite (DP) area fraction measurement

Usage:
    python lom_dashboard.py

Opens a maximised tabbed dashboard with:
    - GC / HPDC / DCC tabs  : 2×2 grid of plots, one Save button per subplot
    - Comparison tab         : one plot per temperature, all 3 casting methods

Uncertainty strategy
--------------------
Cast-level uncertainty is the sample SD of Vv across all repeat scoring
sessions of a representative image for that cast type.  The representative
sample is chosen by the following priority:

  1. Explicit override  — if UNCERTAINTY_OVERRIDE[cast_key] is set to a
     non-None sample name, that sample is always used regardless of how
     many repeats it has.
  2. Auto-discovery    — the sample with the greatest number of
     lom_analysis repeat CSVs in the cast results folder is used.
     Ties are broken alphabetically (deterministic).

The override dict is the only place you need to edit to change which image
drives the uncertainty for a given cast type.  Set an entry to None to
revert to auto-discovery.

The SD and source sample are annotated on every plot so figures are
self-documenting.  Error bars show ±1 SD.  If fewer than 2 repeats exist
for the chosen sample, uncertainty is shown as pending.

Parameters
----------
HIGHLIGHT_REPEATS : bool
VV_YMAX           : float   upper y-axis limit (default 0.6)
RESULTS_BASE      : str
RESULTS_PLOTS     : str
"""

import os

# ── PARAMETERS ────────────────────────────────────────────────────────────────
# ---INSTRUCTIONS ---
# Please set BASE_DIR to the folder where you extracted the Magnesium Masters Project data.
BASE_DIR = r"C:\Path\To\Project"

RESULTS_BASE       = os.path.join(BASE_DIR, "RESULTS")
RESULTS_PLOTS      = os.path.join(BASE_DIR, "RESULTS_PLOTS")
GRAIN_RESULTS_BASE = os.path.join(BASE_DIR, "RESULTS_GRAIN_SIZE")

# Explicit override for which sample drives uncertainty per cast type.
# Set to None to use auto-discovery (sample with most repeats).
UNCERTAINTY_OVERRIDE = {
    "GC":   "GC100",
    "HPDC": "HC100",
    "DCC":  "DC100",
}

HIGHLIGHT_REPEATS = True
VV_YMAX           = 0.6

# Path to grain size results (written by grain_intercept.py + grain_analyse.py)
GRAIN_RESULTS_BASE = (
    r"C:\Users\Monty Imperial\OneDrive - Imperial College London"
    r"\Magnesium Masters Project\RESULTS_GRAIN_SIZE"
)

# Override which sample drives the grain size bar per cast type.
# None  → standard convention: GS, HS, DS
# str   → use this specific sample name (regex bypass)
# HS is overetched; HA4 used as proxy (150 °C / 4 hrs, no grain growth expected).
GRAIN_SAMPLE_OVERRIDE = {
    "GC":   None,    # → GS
    "HPDC": "HA4",   # → HA4  (proxy for HS)
    "DCC":  "DA4",    # → DA4 (proxy for DS)
}

SAVE_DPI = 150
FIG_EXT  = ".png"
# ──────────────────────────────────────────────────────────────────────────────

import os
import re
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.lines as mlines

# ── COLOURS ───────────────────────────────────────────────────────────────────
BG_DARK    = "#1a1a1a"
BG_MID     = "#2a2a2a"
BG_STRIP   = "#111111"
BG_WARN    = "#1C1010"
BG_AMBER   = "#1C1600"
ACCENT     = "#90CAF9"
TEXT_WHITE = "#FFFFFF"
TEXT_DIM   = "#B0BEC5"
RED_WARN   = "#EF5350"
AMBER_WARN = "#FFB300"
BTN_SAVE   = "#37474F"
BTN_HOVER  = "#546E7A"
SPINE_COL  = "#555555"
GRID_COL   = "#444444"

CONDITION_META = {
    "A": dict(label="150 °C", colour="#64B5F6", marker="o"),
    "B": dict(label="175 °C", colour="#FF8A65", marker="s"),
    "C": dict(label="200 °C", colour="#81C784", marker="^"),
}
CAST_META = {
    "GC":   dict(label="Gravity Cast",           colour="#CE93D8", marker="D"),
    "HPDC": dict(label="High-Pressure Die Cast", colour="#FFD54F", marker="o"),
    "DCC":  dict(label="Direct Chill Cast",      colour="#80DEEA", marker="s"),
}
CAST_LETTER  = {"GC": "G", "HPDC": "H", "DCC": "D"}
CAST_FOLDERS = {"GC": "GC", "HPDC": "HPDC", "DCC": "DCC"}
AGING_TIMES  = [4, 19, 43, 67, 100]

# Fixed UI heights in pixels
HDR_H       = 40
TAB_BAR_H   = 36
WARN_LINE_H = 20
BTN_H       = 36


# ═══════════════════════════════════════════════════════════════════════════════
#  UNCERTAINTY DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def _find_analysis_csvs_for_sample(cast_root, sample_name, mag_filter):
    """
    Return list of (repeat_num, Vv) tuples from all lom_analysis CSVs for
    sample_name in cast_root that match mag_filter.
    """
    if mag_filter:
        pat = re.compile(
            rf"^lom_analysis_{re.escape(sample_name)}_{re.escape(mag_filter)}_r(\d+)\.csv$",
            re.IGNORECASE,
        )
    else:
        pat = re.compile(
            rf"^lom_analysis_{re.escape(sample_name)}_r(\d+)\.csv$",
            re.IGNORECASE,
        )

    results = []
    for dirpath, _, filenames in os.walk(cast_root):
        for fn in filenames:
            m = pat.match(fn)
            if m:
                try:
                    df = pd.read_csv(os.path.join(dirpath, fn))
                    if "Vv" in df.columns:
                        results.append((int(m.group(1)), float(df["Vv"].iloc[0])))
                except Exception as e:
                    print(f"[WARN] Could not read {fn}: {e}")
    return results


def discover_uncertainty_sample(cast_root, mag_filter):
    """
    Scan cast_root for all lom_analysis repeat CSVs.  Return a dict mapping
    sample_name -> repeat_count, considering only files matching mag_filter.
    """
    if mag_filter:
        pat = re.compile(
            r"^lom_analysis_(.+?)_"
            + re.escape(mag_filter)
            + r"_r(\d+)\.csv$",
            re.IGNORECASE,
        )
    else:
        pat = re.compile(
            r"^lom_analysis_(.+?)_r(\d+)\.csv$",
            re.IGNORECASE,
        )

    counts = {}
    for dirpath, _, filenames in os.walk(cast_root):
        for fn in filenames:
            m = pat.match(fn)
            if m:
                sample = m.group(1)
                counts[sample] = counts.get(sample, 0) + 1
    return counts


def load_cast_uncertainty(results_base, cast_key, mag_filter):
    """
    Determine the representative sample for cast_key and compute the sample
    SD of Vv across all its repeat analysis CSVs.

    Priority:
        1. UNCERTAINTY_OVERRIDE[cast_key] if not None
        2. Sample with the most repeats (ties broken alphabetically)

    Returns:
        sd          : float or None (None if < 2 repeats available)
        n_repeats   : int
        rep_sample  : str — name of sample used
        source      : str — 'override' or 'auto'
    """
    cast_root = os.path.join(results_base, CAST_FOLDERS.get(cast_key, cast_key))

    if not os.path.isdir(cast_root):
        print(f"[WARN] Cast results folder not found: {cast_root}")
        return None, 0, "—", "—"

    # ── determine representative sample ────────────────────────────────────
    override = UNCERTAINTY_OVERRIDE.get(cast_key)
    if override is not None:
        rep_sample = override
        source     = "override"
    else:
        counts = discover_uncertainty_sample(cast_root, mag_filter)
        if not counts:
            print(f"[INFO] {cast_key}: no repeat CSVs found for auto-discovery.")
            return None, 0, "—", "auto"
        # Most repeats, alphabetical tiebreak
        rep_sample = max(sorted(counts.keys()), key=lambda s: counts[s])
        source     = "auto"

    # ── load Vv values for rep_sample ──────────────────────────────────────
    repeat_data = _find_analysis_csvs_for_sample(cast_root, rep_sample, mag_filter)
    n = len(repeat_data)

    if n < 2:
        print(f"[INFO] {cast_key} uncertainty ({source}): "
              f"only {n} repeat(s) of '{rep_sample}' — need ≥2.")
        return None, n, rep_sample, source

    vv_values = [v for _, v in sorted(repeat_data)]
    sd = float(np.std(vv_values, ddof=1))
    print(f"[INFO] {cast_key} uncertainty ({source}): "
          f"{n} repeats of '{rep_sample}' → SD = {sd:.4f}  "
          f"(values: {[round(v, 4) for v in vv_values]})")
    return sd, n, rep_sample, source


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════════

def find_analysis_csvs(results_base, cast_folder):
    root = os.path.join(results_base, cast_folder)
    if not os.path.isdir(root):
        return []
    pat_new    = re.compile(r"^lom_analysis_.+_((?:\d+(?:\.\d+)?)x)_r\d+\.csv$", re.IGNORECASE)
    pat_legacy = re.compile(r"^lom_analysis_.+_r\d+\.csv$", re.IGNORECASE)
    results = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            m = pat_new.match(fn)
            if m:
                results.append((os.path.join(dirpath, fn), m.group(1).lower()))
                continue
            if pat_legacy.match(fn):
                results.append((os.path.join(dirpath, fn), None))
    return results


def detect_magnifications(results_base, cast_folder):
    found = {mag for _, mag in find_analysis_csvs(results_base, cast_folder)}
    return sorted(found, key=lambda x: (x is None, x))


def pick_magnification(cast_key, mag_tags, parent):
    choice = {"value": "__cancelled__"}

    dlg = tk.Toplevel(parent)
    dlg.title(f"Select magnification — {cast_key}")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.configure(bg=BG_DARK)
    parent.call("wm", "attributes", str(dlg), "-topmost", True)

    tk.Label(
        dlg,
        text=f"Multiple magnifications found for {cast_key}.\nSelect one to plot:",
        bg=BG_DARK, fg=TEXT_WHITE,
        font=("Courier New", 10), pady=10, padx=20,
        justify="left",
    ).pack(anchor="w", padx=20)

    first_val = mag_tags[0] if mag_tags[0] is not None else "__legacy__"
    var = tk.StringVar(value=first_val)
    for tag in mag_tags:
        display = tag if tag is not None else "legacy (no mag tag)"
        val     = tag if tag is not None else "__legacy__"
        tk.Radiobutton(
            dlg, text=display, variable=var, value=val,
            bg=BG_DARK, fg=TEXT_WHITE, selectcolor=BG_MID,
            activebackground=BG_MID, activeforeground=ACCENT,
            font=("Courier New", 10),
        ).pack(anchor="w", padx=32, pady=2)

    def _confirm():
        raw = var.get()
        choice["value"] = None if raw == "__legacy__" else raw
        dlg.destroy()

    def _cancel():
        dlg.destroy()

    btn_frame = tk.Frame(dlg, bg=BG_DARK)
    btn_frame.pack(pady=(10, 16), padx=20, anchor="e")
    tk.Button(btn_frame, text="Cancel", bg=BG_MID, fg=TEXT_WHITE,
              font=("Courier New", 9), relief="flat", padx=10,
              command=_cancel).pack(side="left", padx=(0, 8))
    tk.Button(btn_frame, text="OK", bg=BTN_SAVE, fg=TEXT_WHITE,
              font=("Courier New", 9, "bold"), relief="flat", padx=10,
              command=_confirm).pack(side="left")

    dlg.protocol("WM_DELETE_WINDOW", _cancel)
    parent.wait_window(dlg)
    return choice["value"]


def parse_sample(sample_name):
    if re.match(r"^[GHD](AR|S)$", sample_name, re.IGNORECASE):
        return None
    m = re.match(r"^([GHD])([ABC])(\d+)$", sample_name, re.IGNORECASE)
    if m:
        return m.group(1).upper(), m.group(2).upper(), int(m.group(3))
    return None


def expected_filename(cast_key, cond, t, mag_tag):
    if mag_tag:
        return f"lom_analysis_{CAST_LETTER[cast_key]}{cond}{t}_{mag_tag}_r1.csv"
    return f"lom_analysis_{CAST_LETTER[cast_key]}{cond}{t}_r1.csv"


def load_cast_data(results_base, cast_key, mag_filter):
    """
    Returns (agg_df | None, missing_list).
    Aggregates Vv across repeats per sample using the mean — the SD used
    for error bars is the cast-level uncertainty from load_cast_uncertainty,
    not the within-sample repeat spread here.
    """
    all_paths = find_analysis_csvs(results_base, CAST_FOLDERS[cast_key])
    missing   = []

    if not all_paths:
        missing.append((f"No analysis CSVs found in RESULTS/{CAST_FOLDERS[cast_key]}/", "red"))
        return None, missing

    paths = [p for p, tag in all_paths if tag == mag_filter]
    if not paths:
        mag_label = mag_filter if mag_filter else "legacy"
        missing.append((f"No files found for magnification: {mag_label}", "red"))
        return None, missing

    records        = []
    loaded_samples = set()

    for p in paths:
        try:
            df = pd.read_csv(p)
        except Exception as e:
            missing.append((f"Could not read {os.path.basename(p)}: {e}", "red"))
            continue
        for _, row in df.iterrows():
            parsed = parse_sample(str(row["sample"]))
            if parsed is None:
                continue
            cast, condition, time_hrs = parsed
            records.append({
                "cast": cast, "condition": condition, "time_hrs": time_hrs,
                "Vv": row["Vv"],
            })
            loaded_samples.add((condition, time_hrs))

    if not records:
        missing.append(("All samples are AR/S or unrecognised — nothing to plot.", "red"))
        return None, missing

    raw = pd.DataFrame(records)

    for cond in CONDITION_META:
        for t in AGING_TIMES:
            if (cond, t) not in loaded_samples:
                missing.append((
                    f"File not found: {expected_filename(cast_key, cond, t, mag_filter)}",
                    "red",
                ))

    agg_rows = []
    for (cast, condition, time_hrs), grp in raw.groupby(["cast", "condition", "time_hrs"]):
        agg_rows.append({
            "condition": condition, "time_hrs": time_hrs,
            "n_repeats": len(grp),
            "Vv_mean":   grp["Vv"].mean(),
        })

    agg = pd.DataFrame(agg_rows).sort_values(["condition", "time_hrs"]).reset_index(drop=True)
    return agg, missing


# ═══════════════════════════════════════════════════════════════════════════════
#  PLOT PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════

def style_ax(ax, title):
    ax.set_facecolor(BG_MID)
    for sp in ax.spines.values():
        sp.set_color(SPINE_COL)
    ax.tick_params(colors=TEXT_WHITE, labelsize=8)
    ax.xaxis.label.set_color(TEXT_WHITE)
    ax.yaxis.label.set_color(TEXT_WHITE)
    ax.set_title(title, color=ACCENT, fontsize=9, fontweight="bold", pad=5)
    ax.grid(True, color=GRID_COL, linewidth=0.5, linestyle="--", alpha=0.6)


def set_time_axis(ax, data_times):
    ticks = sorted(set(AGING_TIMES) | {int(t) for t in data_times})
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(t) for t in ticks], fontsize=8)
    ax.set_xlabel("Aging time (hrs)", fontsize=8)
    ax.set_xlim(left=0)


def format_y_axis(ax):
    ax.set_ylabel("V$_v$ — DP area fraction", fontsize=8)
    ax.set_ylim(0, VV_YMAX)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.2f}"))


def _annotate_uncertainty(ax, cast_sd, rep_sample, n_rep, source):
    """
    Add a small text annotation in the bottom-right corner of the axes
    describing the uncertainty source.
    """
    if cast_sd is not None:
        txt = (f"±{cast_sd:.4f} (1 SD, n={n_rep})\n"
               f"src: {rep_sample} [{source}]")
        col = TEXT_DIM
    else:
        txt = f"uncertainty pending\nsrc: {rep_sample} [{source}]"
        col = AMBER_WARN

    ax.text(
        0.99, 0.03, txt,
        transform=ax.transAxes,
        color=col, fontsize=6.5, family="monospace",
        ha="right", va="bottom",
        bbox=dict(facecolor=BG_DARK, edgecolor="none", alpha=0.6, pad=2),
    )


def _plot_series_with_errbar(ax, data, col, mkr, lbl, cast_sd, filled):
    """
    Plot Vv points with symmetric ±1 SD error bars from cast-level uncertainty.
    Open markers flag multi-repeat samples (where Vv_mean is an average).
    cast_sd may be None — in that case points are plotted without error bars.
    """
    if data.empty:
        return

    yerr   = cast_sd if cast_sd is not None else None
    mfc    = col if filled else "none"
    mew    = 0.6 if filled else 1.8
    msz    = 6   if filled else 8
    plbl   = lbl if filled else f"{lbl} (multi-repeat)"

    ax.errorbar(
        data["time_hrs"], data["Vv_mean"],
        yerr=yerr,
        fmt=mkr,
        color=col,
        ecolor=col,
        elinewidth=1.0,
        capsize=3,
        capthick=0.8,
        markersize=msz,
        markerfacecolor=mfc,
        markeredgecolor=col if not filled else TEXT_WHITE,
        markeredgewidth=mew,
        linewidth=0,
        zorder=3,
        label=plbl,
        alpha=0.9,
    )


def plot_condition_series(ax, sub, meta, cast_sd):
    col, mkr, lbl = meta["colour"], meta["marker"], meta["label"]
    ax.plot(sub["time_hrs"], sub["Vv_mean"],
            color=col, linewidth=1.2, zorder=1, alpha=0.7)
    _plot_series_with_errbar(
        ax, sub[sub["n_repeats"] == 1], col, mkr, lbl, cast_sd, filled=True)
    _plot_series_with_errbar(
        ax, sub[sub["n_repeats"] >  1], col, mkr, lbl, cast_sd,
        filled=not HIGHLIGHT_REPEATS)


def plot_cast_series(ax, sub, cast_key, cast_sd):
    meta = CAST_META[cast_key]
    col, mkr, lbl = meta["colour"], meta["marker"], meta["label"]
    ax.plot(sub["time_hrs"], sub["Vv_mean"],
            color=col, linewidth=1.2, zorder=1, alpha=0.7)
    _plot_series_with_errbar(
        ax, sub[sub["n_repeats"] == 1], col, mkr, lbl, cast_sd, filled=True)
    _plot_series_with_errbar(
        ax, sub[sub["n_repeats"] >  1], col, mkr, lbl, cast_sd,
        filled=not HIGHLIGHT_REPEATS)


def add_legend(ax, has_multi=False):
    handles, labels = ax.get_legend_handles_labels()
    seen, h_out, l_out = {}, [], []
    for h, l in zip(handles, labels):
        if l not in seen:
            seen[l] = True; h_out.append(h); l_out.append(l)
    if HIGHLIGHT_REPEATS and has_multi and "Open marker = multi-repeat" not in l_out:
        h_out.append(mlines.Line2D([], [], marker="o", color=TEXT_WHITE,
                                   markerfacecolor="none", markeredgecolor=TEXT_WHITE,
                                   markeredgewidth=1.5, markersize=7, linewidth=0))
        l_out.append("Open marker = multi-repeat")
    if h_out:
        ax.legend(h_out, l_out, fontsize=7.5, framealpha=0.35,
                  labelcolor=TEXT_WHITE, facecolor=BG_MID, edgecolor=SPINE_COL)


def draw_condition_panel(ax, cast_key, agg, cond, unc):
    """
    Render one condition panel.

    unc : dict with keys sd, n, sample, source  (values may be None/0/'—')
    """
    cast_sd    = unc["sd"]
    rep_sample = unc["sample"]
    n_rep      = unc["n"]
    source     = unc["source"]

    title = (f"{cast_key}  —  All temperatures" if cond == "combined"
             else f"{cast_key}  —  {CONDITION_META[cond]['label']} aging")
    style_ax(ax, title)
    format_y_axis(ax)

    if cond == "combined":
        has_any = False; has_multi = False; all_times = []
        if agg is not None:
            for c in ["A", "B", "C"]:
                sub = agg[agg["condition"] == c].sort_values("time_hrs")
                if sub.empty:
                    continue
                has_any = True
                all_times.extend(sub["time_hrs"].tolist())
                plot_condition_series(ax, sub, CONDITION_META[c], cast_sd)
                if (sub["n_repeats"] > 1).any():
                    has_multi = True
        if has_any:
            set_time_axis(ax, all_times)
        else:
            ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                    color=RED_WARN, ha="center", va="center", fontsize=11)
            ax.set_xticks([])
        add_legend(ax, has_multi)
    else:
        if agg is None or agg[agg["condition"] == cond].empty:
            ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                    color=RED_WARN, ha="center", va="center", fontsize=11)
            ax.set_xticks([])
        else:
            sub = agg[agg["condition"] == cond].sort_values("time_hrs")
            plot_condition_series(ax, sub, CONDITION_META[cond], cast_sd)
            set_time_axis(ax, sub["time_hrs"].tolist())
            add_legend(ax, (sub["n_repeats"] > 1).any())

    _annotate_uncertainty(ax, cast_sd, rep_sample, n_rep, source)


def draw_comparison_panel(ax, cond, all_agg, all_unc):
    style_ax(ax, f"Casting comparison  —  {CONDITION_META[cond]['label']} aging")
    format_y_axis(ax)
    all_times = []; has_any = False; has_multi = False
    for ck in ["GC", "HPDC", "DCC"]:
        agg     = all_agg.get(ck)
        cast_sd = all_unc.get(ck, {}).get("sd")
        if agg is None:
            continue
        sub = agg[agg["condition"] == cond].sort_values("time_hrs")
        if sub.empty:
            continue
        has_any = True
        all_times.extend(sub["time_hrs"].tolist())
        plot_cast_series(ax, sub, ck, cast_sd)
        if (sub["n_repeats"] > 1).any():
            has_multi = True
    if has_any:
        set_time_axis(ax, all_times)
    else:
        ax.text(0.5, 0.5, "No data for any casting method",
                transform=ax.transAxes, color=RED_WARN,
                ha="center", va="center", fontsize=10)
        ax.set_xticks([])
    add_legend(ax, has_multi)

    # Annotation lists all three cast uncertainties
    lines = []
    for ck in ["GC", "HPDC", "DCC"]:
        u = all_unc.get(ck, {})
        sd  = u.get("sd")
        smp = u.get("sample", "—")
        n   = u.get("n", 0)
        src = u.get("source", "—")
        if sd is not None:
            lines.append(f"{ck}: ±{sd:.4f} n={n} ({smp}) [{src}]")
        else:
            lines.append(f"{ck}: pending ({smp}) [{src}]")
    ax.text(
        0.99, 0.03, "\n".join(lines),
        transform=ax.transAxes,
        color=TEXT_DIM, fontsize=6.5, family="monospace",
        ha="right", va="bottom",
        bbox=dict(facecolor=BG_DARK, edgecolor="none", alpha=0.6, pad=2),
    )


# ── Standalone save-quality figures ───────────────────────────────────────────
def build_single_figure(cast_key, agg, cond, unc, figsize=(8, 5.5)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG_DARK)
    draw_condition_panel(ax, cast_key, agg, cond, unc)
    fig.tight_layout()
    return fig


def build_comparison_figure(cond, all_agg, all_unc, figsize=(9, 6)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG_DARK)
    draw_comparison_panel(ax, cond, all_agg, all_unc)
    fig.tight_layout()
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
#  TKINTER HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def make_save_button(parent, label, command):
    return tk.Button(
        parent, text=f"💾  {label}",
        bg=BTN_SAVE, fg=TEXT_WHITE,
        activebackground=BTN_HOVER, activeforeground=TEXT_WHITE,
        font=("Courier New", 8, "bold"),
        relief="flat", padx=12, pady=4, cursor="hand2",
        command=command,
    )


def build_missing_panel(parent, missing):
    if not missing:
        return 0
    reds   = [m for m, lv in missing if lv == "red"]
    ambers = [m for m, lv in missing if lv == "amber"]
    total  = 0
    if reds:
        f = tk.Frame(parent, bg=BG_WARN, pady=4, padx=12)
        f.pack(fill="x", pady=(0, 2))
        tk.Label(f, text="⛔  Missing files:",
                 bg=BG_WARN, fg=RED_WARN,
                 font=("Courier New", 9, "bold")).pack(anchor="w")
        for m in reds:
            tk.Label(f, text=f"    •  {m}",
                     bg=BG_WARN, fg=RED_WARN,
                     font=("Courier New", 8)).pack(anchor="w")
        total += (1 + len(reds)) * WARN_LINE_H + 12
    if ambers:
        f = tk.Frame(parent, bg=BG_AMBER, pady=4, padx=12)
        f.pack(fill="x", pady=(2, 0))
        tk.Label(f, text="⚠  Notes:",
                 bg=BG_AMBER, fg=AMBER_WARN,
                 font=("Courier New", 9, "bold")).pack(anchor="w")
        for m in ambers:
            tk.Label(f, text=f"    •  {m}",
                     bg=BG_AMBER, fg=AMBER_WARN,
                     font=("Courier New", 8)).pack(anchor="w")
        total += (1 + len(ambers)) * WARN_LINE_H + 12
    return total


# ═══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

class Dashboard(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("LOM DP Area Fraction Dashboard")
        self.configure(bg=BG_DARK)

        try:
            self.state("zoomed")
        except tk.TclError:
            self.attributes("-zoomed", True)
        self.update_idletasks()

        screen_w_px = self.winfo_screenwidth()
        screen_h_px = self.winfo_screenheight()
        dpi_screen  = self.winfo_fpixels("1i")

        plot_h_px   = screen_h_px - HDR_H - TAB_BAR_H - 2 * BTN_H - 16
        self.fw_in  = screen_w_px / dpi_screen
        self.fh_in  = max(plot_h_px, 300) / dpi_screen
        self.comp_fh_in = (screen_h_px * 0.38) / dpi_screen

        print(f"[INFO] Screen: {screen_w_px}×{screen_h_px}px  "
              f"({dpi_screen:.0f} dpi)  →  "
              f"cast fig = {self.fw_in:.2f}×{self.fh_in:.2f} in")

        # ── Load data ─────────────────────────────────────────────────────
        self.all_agg     = {}
        self.all_missing = {}
        self.all_mag     = {}
        self.all_unc     = {}   # cast_key -> {sd, n, sample, source}

        for cast_key in ["GC", "HPDC", "DCC"]:
            mag_tags = detect_magnifications(RESULTS_BASE, CAST_FOLDERS[cast_key])

            if len(mag_tags) <= 1:
                mag_filter = mag_tags[0] if mag_tags else None
            else:
                mag_filter = pick_magnification(cast_key, mag_tags, self)
                if mag_filter == "__cancelled__":
                    mag_filter = mag_tags[0]

            self.all_mag[cast_key] = mag_filter
            mag_label = mag_filter if mag_filter else "legacy"
            print(f"[INFO] {cast_key}: using magnification = {mag_label}")

            agg, missing = load_cast_data(RESULTS_BASE, cast_key, mag_filter)
            self.all_agg[cast_key]     = agg
            self.all_missing[cast_key] = missing

            # ── uncertainty ───────────────────────────────────────────────
            sd, n_rep, rep_sample, source = load_cast_uncertainty(
                RESULTS_BASE, cast_key, mag_filter
            )
            self.all_unc[cast_key] = {
                "sd":     sd,
                "n":      n_rep,
                "sample": rep_sample,
                "source": source,
            }
            unc_str = (f"SD={sd:.4f} (n={n_rep})"
                       if sd is not None else f"pending (n={n_rep})")
            print(f"[INFO] {cast_key} uncertainty: {unc_str}  "
                  f"src={rep_sample} [{source}]")

        os.makedirs(RESULTS_PLOTS, exist_ok=True)

        # ── Load grain size data ───────────────────────────────────────────
        self.grain_data, self.grain_mag = load_all_grain_data(
            GRAIN_RESULTS_BASE, self
        )

        self._apply_style()
        self._build_ui()

    # ── ttk style ─────────────────────────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook",     background=BG_DARK, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG_MID, foreground=TEXT_DIM,
                    padding=[14, 6], font=("Courier New", 10, "bold"), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", "#263238"), ("active", "#37474F")],
              foreground=[("selected", ACCENT),    ("active", TEXT_WHITE)])
        s.configure("TFrame",      background=BG_DARK)
        s.configure("Dark.TFrame", background=BG_DARK)

    # ── layout ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg=BG_STRIP, height=HDR_H)
        hdr.pack(side="top", fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="LOM  ·  Discontinuous Precipitate Area Fraction Dashboard",
                 bg=BG_STRIP, fg=ACCENT,
                 font=("Courier New", 12, "bold"), pady=8).pack(side="left", padx=16)

        # Uncertainty summary in header
        unc_parts = []
        for ck in ["GC", "HPDC", "DCC"]:
            u  = self.all_unc[ck]
            sd = u["sd"]
            unc_parts.append(
                f"{ck}: {'±'+f'{sd:.4f}' if sd is not None else 'pending'} "
                f"({u['sample']})"
            )
        mag_summary = "   |   ".join(
            f"{ck}: {self.all_mag.get(ck) or 'legacy'}"
            for ck in ["GC", "HPDC", "DCC"]
        )
        tk.Label(hdr,
                 text=f"Uncertainty — {',  '.join(unc_parts)}"
                      f"   |   mag: {mag_summary}",
                 bg=BG_STRIP, fg=TEXT_DIM,
                 font=("Courier New", 8), pady=8).pack(side="right", padx=16)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        for cast_key in ["GC", "HPDC", "DCC"]:
            self._build_cast_tab(cast_key)
        self._build_comparison_tab()
        self._build_grain_size_tab()

    # ── cast tab ──────────────────────────────────────────────────────────────
    def _build_cast_tab(self, cast_key):
        outer = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(outer, text=f"  {cast_key}  ")

        agg     = self.all_agg[cast_key]
        missing = self.all_missing[cast_key]
        unc     = self.all_unc[cast_key]

        warn_frame = tk.Frame(outer, bg=BG_DARK)
        warn_frame.pack(side="top", fill="x")

        # Add uncertainty status to the warning panel if pending
        if unc["sd"] is None:
            missing = list(missing) + [(
                f"Uncertainty pending: need ≥2 repeats of '{unc['sample']}' "
                f"[{unc['source']}]",
                "amber",
            )]
        build_missing_panel(warn_frame, missing)

        fig = plt.figure(figsize=(self.fw_in, self.fh_in), facecolor=BG_DARK)
        gs  = gridspec.GridSpec(
            2, 2, figure=fig,
            hspace=0.45, wspace=0.28,
            left=0.06, right=0.98,
            top=0.93,  bottom=0.10,
        )

        panels = [("A", 0, 0), ("B", 0, 1), ("C", 1, 0), ("combined", 1, 1)]
        for cond, row, col in panels:
            ax = fig.add_subplot(gs[row, col])
            draw_condition_panel(ax, cast_key, agg, cond, unc)

        fig.suptitle(f"{cast_key}  —  DP Area Fraction vs Aging Time",
                     color=TEXT_WHITE, fontsize=11, fontweight="bold")

        canvas = FigureCanvasTkAgg(fig, master=outer)
        canvas.draw()
        canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        plt.close(fig)

        for row_conds in [("A", "B"), ("C", "combined")]:
            btn_row = tk.Frame(outer, bg=BG_DARK, height=BTN_H)
            btn_row.pack(side="top", fill="x", pady=(2, 0))
            btn_row.pack_propagate(False)
            for cond in row_conds:
                lbl = (f"Save  {cast_key}  — All temperatures"
                       if cond == "combined"
                       else f"Save  {cast_key}  — {CONDITION_META[cond]['label']}")
                make_save_button(
                    btn_row, lbl,
                    command=lambda ck=cast_key, ag=agg, c=cond, u=unc:
                        self._save_single(ck, ag, c, u),
                ).pack(side="left", padx=6, pady=2)

    # ── comparison tab ────────────────────────────────────────────────────────
    def _build_comparison_tab(self):
        outer = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(outer, text="  Casting Method Comparison  ")

        scroll_canvas = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0)
        scrolly       = ttk.Scrollbar(outer, orient="vertical",
                                      command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrolly.set)
        scrolly.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)

        inner  = tk.Frame(scroll_canvas, bg=BG_DARK)
        win_id = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>",
                   lambda e: scroll_canvas.configure(
                       scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>",
                           lambda e: scroll_canvas.itemconfig(win_id, width=e.width))
        scroll_canvas.bind_all(
            "<MouseWheel>",
            lambda e: scroll_canvas.yview_scroll(int(-1 * e.delta / 120), "units"),
        )

        comp_missing = [
            (f"{ck}: no data found — not plotted", "red")
            for ck in ["GC", "HPDC", "DCC"]
            if self.all_agg[ck] is None
        ]
        build_missing_panel(inner, comp_missing)

        for cond in ["A", "B", "C"]:
            meta    = CONDITION_META[cond]
            section = tk.Frame(inner, bg=BG_DARK)
            section.pack(fill="x", pady=(10, 0))

            tk.Label(section, text=f"  {meta['label']} aging",
                     bg=BG_STRIP, fg=ACCENT,
                     font=("Courier New", 10, "bold"),
                     pady=4).pack(fill="x")

            fig = plt.figure(figsize=(self.fw_in, self.comp_fh_in),
                             facecolor=BG_DARK)
            ax  = fig.add_subplot(111)
            draw_comparison_panel(ax, cond, self.all_agg, self.all_unc)
            fig.tight_layout()

            fc = FigureCanvasTkAgg(fig, master=section)
            fc.draw()
            fc.get_tk_widget().pack(fill="x")
            plt.close(fig)

            make_save_button(
                section,
                f"Save comparison — {meta['label']}",
                command=lambda c=cond: self._save_comparison(c),
            ).pack(pady=(4, 2))

    # ── save handlers ─────────────────────────────────────────────────────────
    def _save_single(self, cast_key, agg, cond, unc):
        tag   = ("combined" if cond == "combined"
                 else CONDITION_META[cond]["label"].replace(" ", "").replace("°", "deg"))
        fig   = build_single_figure(cast_key, agg, cond, unc, figsize=(8, 5.5))
        fname = os.path.join(RESULTS_PLOTS, f"{cast_key}_Vv_{tag}{FIG_EXT}")
        fig.savefig(fname, dpi=SAVE_DPI, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        messagebox.showinfo("Saved", f"Figure saved to:\n{fname}", parent=self)
        print(f"[INFO] Saved → {fname}")

    def _save_comparison(self, cond):
        label = CONDITION_META[cond]["label"].replace(" ", "").replace("°", "deg")
        fig   = build_comparison_figure(cond, self.all_agg, self.all_unc,
                                        figsize=(9, 6))
        fname = os.path.join(RESULTS_PLOTS, f"comparison_{label}{FIG_EXT}")
        fig.savefig(fname, dpi=SAVE_DPI, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        messagebox.showinfo("Saved", f"Figure saved to:\n{fname}", parent=self)
        print(f"[INFO] Saved → {fname}")

    def _save_grain_size(self):
        fig   = build_grain_size_figure(self.grain_data, self.grain_mag,
                                        figsize=(10, 6))
        fname = os.path.join(RESULTS_PLOTS, f"grain_size_AR_S{FIG_EXT}")
        fig.savefig(fname, dpi=SAVE_DPI, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        messagebox.showinfo("Saved", f"Figure saved to:\n{fname}", parent=self)
        print(f"[INFO] Saved → {fname}")

    def _save_grain_correlation(self):
        fig   = build_grain_correlation_figure(
            self.grain_data, self.all_agg, self.all_unc, figsize=(10, 6)
        )
        fname = os.path.join(RESULTS_PLOTS, f"grain_size_vs_max_Vv{FIG_EXT}")
        fig.savefig(fname, dpi=SAVE_DPI, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        messagebox.showinfo("Saved", f"Figure saved to:\n{fname}", parent=self)
        print(f"[INFO] Saved → {fname}")

    def _save_grain_scatter(self):
        fig   = build_grain_scatter_figure(
            self.grain_data, self.all_agg, self.all_unc, figsize=(8, 6)
        )
        fname = os.path.join(RESULTS_PLOTS, f"grain_size_scatter{FIG_EXT}")
        fig.savefig(fname, dpi=SAVE_DPI, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        messagebox.showinfo("Saved", f"Figure saved to:\n{fname}", parent=self)
        print(f"[INFO] Saved → {fname}")

    # ── grain size tab ────────────────────────────────────────────────────────
    def _build_grain_size_tab(self):
        outer = ttk.Frame(self.nb, style="Dark.TFrame")
        self.nb.add(outer, text="  Grain Size  ")

        # Scrollable container so two figures fit without clipping
        scroll_canvas = tk.Canvas(outer, bg=BG_DARK, highlightthickness=0)
        scrolly       = ttk.Scrollbar(outer, orient="vertical",
                                      command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrolly.set)
        scrolly.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)

        inner  = tk.Frame(scroll_canvas, bg=BG_DARK)
        win_id = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: scroll_canvas.configure(
                       scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>",
                           lambda e: scroll_canvas.itemconfig(win_id, width=e.width))
        scroll_canvas.bind_all(
            "<MouseWheel>",
            lambda e: scroll_canvas.yview_scroll(int(-1 * e.delta / 120), "units"),
        )

        # ── Warning/info panel ────────────────────────────────────────────────────────────────────────────────────────
        warn_frame = tk.Frame(inner, bg=BG_DARK)
        warn_frame.pack(side="top", fill="x")

        missing = []
        if self.grain_data is None or self.grain_data.empty:
            missing.append(("No grain_analysis CSVs found in RESULTS_GRAIN_SIZE. "
                             "Run grain_intercept.py + grain_analyse.py first.", "red"))
        else:
            for cast_key in ["GC", "HPDC", "DCC"]:
                target = _resolved_sample(cast_key)
                proxy  = _is_proxy(cast_key)
                sub    = self.grain_data[self.grain_data["cast_key"] == cast_key]
                if sub.empty:
                    label = f"{cast_key} ({target}{'  ← proxy' if proxy else ''})"
                    missing.append((f"{label}: no grain_analysis files found", "red"))
                else:
                    n_rep = int(sub.iloc[0]["n_repeats"])
                    if n_rep < 5:
                        label = f"{cast_key} ({target}{'  ← proxy' if proxy else ''})"
                        missing.append((
                            f"{label}: only {n_rep}/5 repeats — "
                            f"SD will be imprecise", "amber"
                        ))
        build_missing_panel(warn_frame, missing)

        fh = max(self.fh_in * 0.60, 4.0)

        # ── Figure 1: grain size bar chart ──────────────────────────────────────────────────────────────────
        fig1 = plt.figure(figsize=(self.fw_in, fh), facecolor=BG_DARK)
        ax1  = fig1.add_subplot(111)
        draw_grain_size_panel(ax1, self.grain_data, self.grain_mag)
        fig1.tight_layout()

        canvas1 = FigureCanvasTkAgg(fig1, master=inner)
        canvas1.draw()
        canvas1.get_tk_widget().pack(side="top", fill="x")
        plt.close(fig1)

        btn_row1 = tk.Frame(inner, bg=BG_DARK, height=BTN_H)
        btn_row1.pack(side="top", fill="x", pady=(2, 8))
        btn_row1.pack_propagate(False)
        make_save_button(
            btn_row1, "Save grain size chart",
            command=self._save_grain_size,
        ).pack(side="left", padx=6, pady=2)

        # ── Figure 2: reciprocal grain size vs max Vv ────────────────────────────────────────────────────
        fig2 = plt.figure(figsize=(self.fw_in, fh), facecolor=BG_DARK)
        ax2  = fig2.add_subplot(111)
        draw_grain_correlation_panel(ax2, self.grain_data, self.all_agg, self.all_unc)
        fig2.tight_layout()

        canvas2 = FigureCanvasTkAgg(fig2, master=inner)
        canvas2.draw()
        canvas2.get_tk_widget().pack(side="top", fill="x")
        plt.close(fig2)

        btn_row2 = tk.Frame(inner, bg=BG_DARK, height=BTN_H)
        btn_row2.pack(side="top", fill="x", pady=(2, 8))
        btn_row2.pack_propagate(False)
        make_save_button(
            btn_row2, "Save reciprocal grain size vs max Vv chart",
            command=self._save_grain_correlation,
        ).pack(side="left", padx=6, pady=2)

        # ── Figure 3: scatter plot 1/l̅ vs max Vv ──────────────────────────────────────────────
        fig3 = plt.figure(figsize=(self.fw_in, fh), facecolor=BG_DARK)
        ax3  = fig3.add_subplot(111)
        draw_grain_scatter_panel(ax3, self.grain_data, self.all_agg, self.all_unc)
        fig3.tight_layout()

        canvas3 = FigureCanvasTkAgg(fig3, master=inner)
        canvas3.draw()
        canvas3.get_tk_widget().pack(side="top", fill="x")
        plt.close(fig3)

        btn_row3 = tk.Frame(inner, bg=BG_DARK, height=BTN_H)
        btn_row3.pack(side="top", fill="x", pady=(2, 8))
        btn_row3.pack_propagate(False)
        make_save_button(
            btn_row3, "Save 1/l̅ vs max Vv scatter",
            command=self._save_grain_scatter,
        ).pack(side="left", padx=6, pady=2)

# ═══════════════════════════════════════════════════════════════════════════════
#  GRAIN SIZE DATA LAYER
# ═══════════════════════════════════════════════════════════════════════════════

GRAIN_CAST_FOLDERS = {"GC": "GC", "HPDC": "HPDC", "DCC": "DCC"}

# Standard solutionised sample names per cast (used when override is None)
_GRAIN_STANDARD = {
    "GC":   "GS",
    "HPDC": "HS",
    "DCC":  "DS",
}


def _resolved_sample(cast_key):
    """Return the sample name to use for grain size, respecting overrides."""
    override = GRAIN_SAMPLE_OVERRIDE.get(cast_key)
    return override if override is not None else _GRAIN_STANDARD[cast_key]


def _is_proxy(cast_key):
    """Return True if an override sample is being used instead of the standard one."""
    return GRAIN_SAMPLE_OVERRIDE.get(cast_key) is not None


def detect_grain_magnifications(grain_results_base, cast_folder):
    """Return sorted list of mag tags found in grain_analysis CSVs for cast."""
    root = os.path.join(grain_results_base, cast_folder)
    if not os.path.isdir(root):
        return []
    pat = re.compile(
        r"^grain_analysis_.+_((?:\d+(?:\.\d+)?)x)_r\d+\.csv$", re.IGNORECASE
    )
    mags = set()
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            m = pat.match(fn)
            if m:
                mags.add(m.group(1).lower())
    return sorted(mags)


def load_grain_analysis_csvs(grain_results_base, cast_key, mag_filter):
    """
    Load all grain_analysis CSVs for the resolved sample for cast_key.

    The target sample is determined by GRAIN_SAMPLE_OVERRIDE:
      - None  → standard name (GS / HS / DS)
      - str   → that exact sample name (regex bypass)

    Returns list of dicts: cast_key, sample, condition, G, repeat, mag_tag,
                           is_proxy.
    """
    cast_root   = os.path.join(grain_results_base, GRAIN_CAST_FOLDERS[cast_key])
    target      = _resolved_sample(cast_key)
    proxy       = _is_proxy(cast_key)

    if not os.path.isdir(cast_root):
        return []

    if mag_filter:
        pat = re.compile(
            rf"^grain_analysis_{re.escape(target)}_{re.escape(mag_filter)}_r(\d+)\.csv$",
            re.IGNORECASE,
        )
    else:
        pat = re.compile(
            rf"^grain_analysis_{re.escape(target)}_r(\d+)\.csv$",
            re.IGNORECASE,
        )

    records = []
    for dirpath, _, filenames in os.walk(cast_root):
        for fn in filenames:
            m = pat.match(fn)
            if not m:
                continue
            try:
                df = pd.read_csv(os.path.join(dirpath, fn))
                if "G" not in df.columns or df["G"].isna().all():
                    continue
                G      = float(df["G"].iloc[0])
                repeat = int(df["repeat"].iloc[0]) if "repeat" in df.columns else int(m.group(1))
                mag_tag = str(df["mag_tag"].iloc[0]) if "mag_tag" in df.columns else (mag_filter or "")
                records.append({
                    "cast_key":  cast_key,
                    "sample":    target,
                    "condition": "S",       # always treated as solutionised for display
                    "G":         G,
                    "repeat":    repeat,
                    "mag_tag":   mag_tag,
                    "is_proxy":  proxy,
                })
            except Exception as e:
                print(f"[WARN] Could not read {fn}: {e}")

    return records


def G_to_intercept_um(G):
    """
    Inverse of ASTM E112-25 Eq A1.6:
        G = 6.643856 × log10(N̄_L) − 3.288   (N̄_L in mm⁻¹)
    →   N̄_L = 10^((G + 3.288) / 6.643856)
    →   l̄   = 1 / N̄_L [mm] × 1000  [µm]

    Works for any real G, including negative values (large grains).
    Returns None on error.
    """
    try:
        NL_per_mm = 10 ** ((G + 3.288) / 6.643856)
        return (1.0 / NL_per_mm) * 1000.0
    except Exception:
        return None


def aggregate_grain_data(records):
    """
    Compute mean G, SD of G, mean intercept (µm) and SD of intercept (µm)
    per (cast_key, sample).

    µm statistics are computed per-repeat in µm space (not propagated from
    G SD) so they remain physically meaningful for large-grain / negative-G
    samples where the G→µm relationship is highly nonlinear.

    Returns DataFrame with columns:
        cast_key, sample, condition, n_repeats,
        G_mean, G_sd,
        intercept_um_mean, intercept_um_sd,
        is_proxy
    """
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    rows = []
    for (cast_key, sample), grp in df.groupby(["cast_key", "sample"]):
        G_vals  = grp["G"].dropna().tolist()
        n       = len(G_vals)
        um_vals = [v for v in (G_to_intercept_um(g) for g in G_vals)
                   if v is not None]
        rows.append({
            "cast_key":          cast_key,
            "sample":            sample,
            "condition":         "S",
            "n_repeats":         n,
            "G_mean":            float(np.mean(G_vals))           if n > 0          else None,
            "G_sd":              float(np.std(G_vals, ddof=1))    if n > 1          else None,
            "intercept_um_mean": float(np.mean(um_vals))          if um_vals        else None,
            "intercept_um_sd":   float(np.std(um_vals, ddof=1))   if len(um_vals) > 1 else None,
            "is_proxy":          bool(grp["is_proxy"].iloc[0]),
        })
    return pd.DataFrame(rows).sort_values("cast_key").reset_index(drop=True)


def load_all_grain_data(grain_results_base, parent_widget):
    """
    Load and aggregate grain size data for all three cast types.
    Returns (agg_df | None, mag_dict).
    """
    all_records = []
    mag_dict    = {}

    for cast_key in ["GC", "HPDC", "DCC"]:
        mags = detect_grain_magnifications(grain_results_base, GRAIN_CAST_FOLDERS[cast_key])
        if len(mags) == 0:
            mag_filter = None
        elif len(mags) == 1:
            mag_filter = mags[0]
        else:
            mag_filter = pick_magnification(cast_key, mags, parent_widget)
            if mag_filter == "__cancelled__":
                mag_filter = mags[0]

        mag_dict[cast_key] = mag_filter
        target    = _resolved_sample(cast_key)
        proxy_str = f" [proxy: {target}]" if _is_proxy(cast_key) else ""
        print(f"[INFO] Grain size {cast_key}: sample={target}{proxy_str}  mag={mag_filter or 'n/a'}")

        records = load_grain_analysis_csvs(grain_results_base, cast_key, mag_filter)
        print(f"[INFO] Grain size {cast_key}: {len(records)} repeat(s) loaded")
        all_records.extend(records)

    if not all_records:
        print("[INFO] No grain size analysis files found.")
        return None, mag_dict

    agg = aggregate_grain_data(all_records)
    return agg, mag_dict


# ═══════════════════════════════════════════════════════════════════════════════
#  GRAIN SIZE PLOT
# ═══════════════════════════════════════════════════════════════════════════════

def build_grain_size_figure(grain_data, grain_mag, figsize=(10, 6)):
    """
    Bar chart: mean lineal intercept l̄ (µm) per casting method.
    Error bars show ±1 SD computed per-repeat in µm space.
    """
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG_DARK)
    draw_grain_size_panel(ax, grain_data, grain_mag)
    fig.tight_layout()
    return fig


def draw_grain_size_panel(ax, grain_data, grain_mag):
    """
    Single-axis bar chart: mean lineal intercept l̄ (µm) per casting method.
    ASTM G is retained in the data layer for traceability but not plotted —
    µm is the physically meaningful quantity and handles negative G correctly.
    Error bars show ±1 SD computed per-repeat in µm space.
    """
    cast_keys = ["GC", "HPDC", "DCC"]
    bar_w     = 0.45
    x_pos     = list(range(len(cast_keys)))
    colours   = [CAST_META[ck]["colour"] for ck in cast_keys]

    # ── axes styling ─────────────────────────────────────────────────────
    ax.set_facecolor(BG_MID)
    for sp in ax.spines.values():
        sp.set_color(SPINE_COL)
    ax.tick_params(colors=TEXT_WHITE, labelsize=9)
    ax.xaxis.label.set_color(TEXT_WHITE)
    ax.yaxis.label.set_color(TEXT_WHITE)
    ax.set_title(
    "Mean Lineal Intercept  l\u0305  —  Solutionised State\n"
    "(GC: GS direct;  HPDC: HA4 proxy;  DCC: DA4 proxy — 150 °C 4 hrs, no grain growth expected)",
    color=ACCENT, fontsize=9, fontweight="bold", pad=8,
    )
    ax.set_ylabel("Mean Lineal Intercept  l\u0305  (µm)", fontsize=9, color=TEXT_WHITE)
    ax.grid(True, axis="y", color=GRID_COL, linewidth=0.5,
            linestyle="--", alpha=0.5, zorder=0)

    if grain_data is None or grain_data.empty:
        ax.text(0.5, 0.5, "No grain size data found",
                transform=ax.transAxes, color=RED_WARN,
                ha="center", va="center", fontsize=12)
        ax.set_xticks(x_pos)
        ax.set_xticklabels([CAST_META[ck]["label"] for ck in cast_keys],
                           color=TEXT_WHITE, fontsize=9)
        return

    # ── first pass: collect µm values to set y-limit ──────────────────────
    all_um_tops = []
    for cast_key in cast_keys:
        sub = grain_data[grain_data["cast_key"] == cast_key]
        if sub.empty:
            continue
        row  = sub.iloc[0]
        u    = row["intercept_um_mean"]
        u_sd = row["intercept_um_sd"]
        if u is not None and not _is_nan(u):
            top = float(u) + (float(u_sd) if (u_sd is not None and not _is_nan(u_sd)) else 0.0)
            all_um_tops.append(top)

    if all_um_tops:
        ax.set_ylim(0, max(all_um_tops) * 1.55)

    # ── second pass: draw bars ────────────────────────────────────────────
    for i, cast_key in enumerate(cast_keys):
        col = colours[i]
        sub = grain_data[grain_data["cast_key"] == cast_key]

        if sub.empty or sub["intercept_um_mean"].isna().all():
            ax.bar(x_pos[i], 0, width=bar_w,
                   color="none", edgecolor=SPINE_COL,
                   linewidth=1.2, linestyle="--")
            ax.text(x_pos[i], ax.get_ylim()[1] * 0.05, "no data",
                    ha="center", va="bottom",
                    color=RED_WARN, fontsize=8, family="monospace")
            continue

        row      = sub.iloc[0]
        um_mean  = float(row["intercept_um_mean"])
        um_sd    = row["intercept_um_sd"]
        G_mean   = row["G_mean"]
        n_rep    = int(row["n_repeats"])
        is_proxy = bool(row["is_proxy"]) if "is_proxy" in row.index else False
        sample   = str(row["sample"])
        proxy_line = f"[proxy: {sample}]" if is_proxy else f"[{sample}]"

        has_um_sd = um_sd is not None and not _is_nan(um_sd)
        has_G     = G_mean is not None and not _is_nan(G_mean)

        ax.bar(x_pos[i], um_mean, width=bar_w,
               color=col, alpha=0.85,
               edgecolor=TEXT_WHITE, linewidth=0.9, zorder=3)

        if has_um_sd:
            ax.errorbar(x_pos[i], um_mean, yerr=float(um_sd),
                        fmt="none", ecolor=TEXT_WHITE,
                        elinewidth=1.3, capsize=5, capthick=1.0, zorder=5)

        um_sd_str = f"±{um_sd:.1f} µm" if has_um_sd else "SD n/a"
        g_str     = f"G = {G_mean:.2f}" if has_G else ""
        tip       = um_mean + (float(um_sd) if has_um_sd else 0.0)
        ann_y     = tip + ax.get_ylim()[1] * 0.02

        ax.text(x_pos[i], ann_y,
                f"{um_mean:.1f} µm\n{um_sd_str}\nn={n_rep}\n{g_str}\n{proxy_line}",
                ha="center", va="bottom",
                color=TEXT_WHITE, fontsize=7.5, family="monospace", zorder=6)

    # ── x-axis ───────────────────────────────────────────────────────────
    ax.set_xticks(x_pos)
    ax.set_xticklabels([CAST_META[ck]["label"] for ck in cast_keys],
                       color=TEXT_WHITE, fontsize=9)
    ax.set_xlim(-0.6, len(cast_keys) - 0.4)

    # ── magnification annotation ──────────────────────────────────────────
    mag_parts = [f"{ck}: {grain_mag.get(ck) or 'n/a'}" for ck in cast_keys]
    ax.text(0.99, 0.02, "mag: " + "  |  ".join(mag_parts),
            transform=ax.transAxes, color=TEXT_DIM,
            fontsize=7, family="monospace", ha="right", va="bottom",
            bbox=dict(facecolor=BG_DARK, edgecolor="none", alpha=0.6, pad=2))


def compute_max_vv(all_agg):
    """
    Return dict {cast_key: max_Vv} — peak Vv across all conditions and
    aging times for each cast type.  Returns None for casts with no data.
    """
    result = {}
    for cast_key in ["GC", "HPDC", "DCC"]:
        agg = all_agg.get(cast_key)
        if agg is None or agg.empty:
            result[cast_key] = None
        else:
            result[cast_key] = float(agg["Vv_mean"].max())
    return result


def build_grain_correlation_figure(grain_data, all_agg, all_unc, figsize=(10, 6)):
    """
    Bar chart: reciprocal mean lineal intercept 1/l̅ (mm⁻¹) on LHS,
    maximum DP area fraction Vv on RHS.
    """
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG_DARK)
    draw_grain_correlation_panel(ax, grain_data, all_agg, all_unc)
    fig.tight_layout()
    return fig


def draw_grain_correlation_panel(ax_left, grain_data, all_agg, all_unc=None):
    """
    Grouped bar chart per casting method:
      Left y-axis  (solid bar)   : 1/l̅ in mm⁻¹ (reciprocal mean intercept)
      Right y-axis (hatched bar) : max Vv (peak DP area fraction across all
                                   conditions and aging times), with ±1 SD
                                   error bars from cast-level uncertainty.
    """
    import matplotlib.patches as mpatches

    cast_keys = ["GC", "HPDC", "DCC"]
    bar_w     = 0.32
    gap       = 0.06
    x_pos     = list(range(len(cast_keys)))
    colours   = [CAST_META[ck]["colour"] for ck in cast_keys]
    x_left    = [x - bar_w / 2 - gap / 2 for x in x_pos]
    x_right   = [x + bar_w / 2 + gap / 2 for x in x_pos]

    ax_right = ax_left.twinx()

    for ax in (ax_left, ax_right):
        ax.set_facecolor(BG_MID)
        for sp in ax.spines.values():
            sp.set_color(SPINE_COL)
        ax.tick_params(colors=TEXT_WHITE, labelsize=9)

    ax_left.set_title(
        "Reciprocal Grain Size  vs  Maximum DP Area Fraction\n"
        "( 1/l̅ ∝ grain boundary density — both axes should track together )",
        color=ACCENT, fontsize=9, fontweight="bold", pad=8,
    )
    ax_left.set_ylabel("Reciprocal Mean Intercept  1/l̅  (mm⁻¹)",
                       fontsize=9, color=ACCENT)
    ax_right.set_ylabel("Maximum DP Area Fraction  Vᵥ  (peak across all conditions)",
                        fontsize=9, color=TEXT_WHITE)
    ax_left.yaxis.label.set_color(ACCENT)
    ax_right.yaxis.label.set_color(TEXT_WHITE)
    ax_left.tick_params(axis="y", colors=ACCENT)
    ax_right.tick_params(axis="y", colors=TEXT_WHITE)
    ax_left.grid(True, axis="y", color=GRID_COL, linewidth=0.5,
                 linestyle="--", alpha=0.5, zorder=0)

    max_vv = compute_max_vv(all_agg)

    recip_vals = []
    vv_tops    = []   # vv + sd for ylim calculation
    for cast_key in cast_keys:
        if grain_data is not None and not grain_data.empty:
            sub = grain_data[grain_data["cast_key"] == cast_key]
            if not sub.empty:
                um = sub.iloc[0]["intercept_um_mean"]
                if um is not None and not _is_nan(um) and float(um) > 0:
                    recip_vals.append(1.0 / (float(um) / 1000.0))
        vv = max_vv.get(cast_key)
        if vv is not None:
            sd = (all_unc or {}).get(cast_key, {}).get("sd")
            vv_tops.append(vv + (float(sd) if sd is not None and not _is_nan(sd) else 0.0))

    if recip_vals:
        ax_left.set_ylim(0, max(recip_vals) * 2.2)
    if vv_tops:
        ax_right.set_ylim(0, max(vv_tops) * 2.2)

    if (grain_data is None or grain_data.empty) and not any(vv_vals):
        ax_left.text(0.5, 0.5, "No data available",
                     transform=ax_left.transAxes, color=RED_WARN,
                     ha="center", va="center", fontsize=12)
        ax_left.set_xticks(x_pos)
        ax_left.set_xticklabels([CAST_META[ck]["label"] for ck in cast_keys],
                                color=TEXT_WHITE, fontsize=9)
        return

    for i, cast_key in enumerate(cast_keys):
        col = colours[i]

        # ── left bar: 1/l̅ in mm⁻¹ ───────────────────────────────────────────────────────────────────────────────────────────────
        recip_mean = None
        recip_sd   = None
        if grain_data is not None and not grain_data.empty:
            sub = grain_data[grain_data["cast_key"] == cast_key]
            if not sub.empty:
                row   = sub.iloc[0]
                um    = row["intercept_um_mean"]
                um_sd = row["intercept_um_sd"]
                if um is not None and not _is_nan(um) and float(um) > 0:
                    um_f       = float(um)
                    recip_mean = 1.0 / (um_f / 1000.0)
                    if um_sd is not None and not _is_nan(um_sd):
                        # Error propagation: σ(1/l̅) ≈ σ_l̅ / l̅²  (units in mm)
                        recip_sd = float(um_sd) / 1000.0 / (um_f / 1000.0) ** 2

        if recip_mean is not None:
            ax_left.bar(x_left[i], recip_mean, width=bar_w,
                        color=col, alpha=0.85,
                        edgecolor=TEXT_WHITE, linewidth=0.9, zorder=3)
            if recip_sd is not None:
                ax_left.errorbar(x_left[i], recip_mean, yerr=recip_sd,
                                 fmt="none", ecolor=TEXT_WHITE,
                                 elinewidth=1.3, capsize=4, capthick=1.0, zorder=5)
            sd_str = f"±{recip_sd:.3f}" if recip_sd is not None else "SD n/a"
            tip_l  = recip_mean + (recip_sd if recip_sd is not None else 0.0)
            ax_left.text(x_left[i], tip_l + ax_left.get_ylim()[1] * 0.02,
                         f"{recip_mean:.3f} mm⁻¹\n{sd_str}",
                         ha="center", va="bottom",
                         color=ACCENT, fontsize=7.5, family="monospace", zorder=6)
        else:
            ax_left.text(x_left[i], ax_left.get_ylim()[1] * 0.05,
                         "no data", ha="center", va="bottom",
                         color=RED_WARN, fontsize=8, family="monospace")

        # ── right bar: max Vv ──────────────────────────────────────────────────────────────────────────────────────────────────────────
        vv = max_vv.get(cast_key)
        if vv is not None:
            vv_sd = (all_unc or {}).get(cast_key, {}).get("sd")
            has_vv_sd = vv_sd is not None and not _is_nan(vv_sd)
            ax_right.bar(x_right[i], vv, width=bar_w,
                         color=col, alpha=0.45,
                         edgecolor=col, linewidth=1.5,
                         hatch="///", zorder=3)
            if has_vv_sd:
                ax_right.errorbar(x_right[i], vv, yerr=float(vv_sd),
                                  fmt="none", ecolor=col,
                                  elinewidth=1.3, capsize=4, capthick=1.0, zorder=5)
            vv_sd_str = f"±{vv_sd:.4f}" if has_vv_sd else "SD n/a"
            tip_r = vv + (float(vv_sd) if has_vv_sd else 0.0) + ax_right.get_ylim()[1] * 0.02
            ax_right.text(x_right[i], tip_r,
                          f"max Vᵥ\n{vv:.4f}\n{vv_sd_str}",
                          ha="center", va="bottom",
                          color=TEXT_WHITE, fontsize=7.5, family="monospace", zorder=6)
        else:
            ax_right.text(x_right[i], ax_right.get_ylim()[1] * 0.05,
                          "no data", ha="center", va="bottom",
                          color=RED_WARN, fontsize=8, family="monospace")

    ax_left.set_xticks(x_pos)
    ax_left.set_xticklabels([CAST_META[ck]["label"] for ck in cast_keys],
                            color=TEXT_WHITE, fontsize=9)
    ax_left.set_xlim(-0.6, len(cast_keys) - 0.4)

    h_recip = mpatches.Patch(facecolor="grey", alpha=0.85, edgecolor=TEXT_WHITE,
                              label="1/l̅  reciprocal grain size (left axis, mm⁻¹)")
    h_vv    = mpatches.Patch(facecolor="grey", alpha=0.45, edgecolor="grey",
                              hatch="///", label="Max Vᵥ  DP area fraction (right axis)")
    ax_left.legend(handles=[h_recip, h_vv], fontsize=7.5, framealpha=0.35,
                   labelcolor=TEXT_WHITE, facecolor=BG_MID, edgecolor=SPINE_COL,
                   loc="upper left")


def build_grain_scatter_figure(grain_data, all_agg, all_unc, figsize=(8, 6)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(BG_DARK)
    draw_grain_scatter_panel(ax, grain_data, all_agg, all_unc)
    fig.tight_layout()
    return fig


def draw_grain_scatter_panel(ax, grain_data, all_agg, all_unc=None):
    """
    Scatter plot: x = 1/l̅ (mm⁻¹, reciprocal mean intercept),
                  y = max Vv (peak DP area fraction).
    One point per casting method, labelled, with error bars on x from
    propagated σ(1/l̅) and error bars on y from the cast-level
    measurement uncertainty (SD across repeat scorings, same as all
    other DP plots).  A finer grain (higher 1/l̅) is expected to
    correlate with a higher max Vv.
    """
    ax.set_facecolor(BG_MID)
    for sp in ax.spines.values():
        sp.set_color(SPINE_COL)
    ax.tick_params(colors=TEXT_WHITE, labelsize=9)
    ax.xaxis.label.set_color(TEXT_WHITE)
    ax.yaxis.label.set_color(TEXT_WHITE)
    ax.set_title(
        "Reciprocal Grain Size  vs  Peak DP Area Fraction\n"
        "( one point per casting method )",
        color=ACCENT, fontsize=9, fontweight="bold", pad=8,
    )
    ax.set_xlabel("Reciprocal Mean Intercept  1/l̅  (mm⁻¹)", fontsize=9)
    ax.set_ylabel("Maximum DP Area Fraction  Vᵥ", fontsize=9)
    ax.grid(True, color=GRID_COL, linewidth=0.5, linestyle="--", alpha=0.5, zorder=0)

    cast_keys  = ["GC", "HPDC", "DCC"]
    max_vv     = compute_max_vv(all_agg)

    points = []   # (cast_key, x, x_err, y, y_err)
    for cast_key in cast_keys:
        # x: reciprocal intercept
        x = x_err = None
        if grain_data is not None and not grain_data.empty:
            sub = grain_data[grain_data["cast_key"] == cast_key]
            if not sub.empty:
                row   = sub.iloc[0]
                um    = row["intercept_um_mean"]
                um_sd = row["intercept_um_sd"]
                if um is not None and not _is_nan(um) and float(um) > 0:
                    um_f  = float(um)
                    x     = 1.0 / (um_f / 1000.0)
                    if um_sd is not None and not _is_nan(um_sd):
                        x_err = float(um_sd) / 1000.0 / (um_f / 1000.0) ** 2

        # y: peak Vv
        y = max_vv.get(cast_key)

        # y uncertainty: cast-level SD from all_unc (same as other DP plots)
        y_err = None
        if all_unc is not None:
            sd = all_unc.get(cast_key, {}).get("sd")
            if sd is not None and not _is_nan(sd):
                y_err = float(sd)

        if x is not None and y is not None:
            points.append((cast_key, x, x_err, y, y_err))

    if not points:
        ax.text(0.5, 0.5, "Insufficient data for scatter plot",
                transform=ax.transAxes, color=RED_WARN,
                ha="center", va="center", fontsize=11)
        return

    # Axis limits with padding — account for error bar extents
    xs    = [p[1] for p in points]
    ys    = [p[3] for p in points]
    x_tops = [p[1] + (p[2] or 0) for p in points]
    y_tops = [p[3] + (p[4] or 0) for p in points]
    x_pad = (max(xs) - min(xs)) * 0.35 if len(xs) > 1 else max(xs) * 0.5
    y_pad = (max(ys) - min(ys)) * 0.35 if len(ys) > 1 else max(ys) * 0.5
    ax.set_xlim(max(0, min(xs) - x_pad), max(x_tops) + x_pad)
    ax.set_ylim(max(0, min(ys) - y_pad), max(y_tops) + y_pad)

    for cast_key, x, x_err, y, y_err in points:
        meta = CAST_META[cast_key]
        col  = meta["colour"]
        mkr  = meta["marker"]
        lbl  = meta["label"]

        ax.errorbar(x, y,
                    xerr=x_err if x_err is not None else 0,
                    yerr=y_err if y_err is not None else 0,
                    fmt=mkr, color=col,
                    ecolor=col, elinewidth=1.2,
                    capsize=4, capthick=1.0,
                    markersize=12, markeredgecolor=TEXT_WHITE,
                    markeredgewidth=0.8,
                    zorder=4, label=lbl)

        # Label offset: nudge right and up slightly
        x_range = ax.get_xlim()[1] - ax.get_xlim()[0]
        y_range = ax.get_ylim()[1] - ax.get_ylim()[0]
        y_err_str = f"±{y_err:.4f}" if y_err is not None else "SD n/a"
        ax.text(x + x_range * 0.03, y + y_range * 0.03,
                f"{cast_key}\n1/l̅={x:.3f}\nVv={y:.4f} ({y_err_str})",
                color=TEXT_WHITE, fontsize=7.5, family="monospace",
                va="bottom", zorder=5)

    # Best-fit line if 3 points available
    if len(points) == 3:
        import numpy as np
        xs_arr = np.array([p[1] for p in points])
        ys_arr = np.array([p[3] for p in points])
        m, b   = np.polyfit(xs_arr, ys_arr, 1)
        x_fit  = np.linspace(ax.get_xlim()[0], ax.get_xlim()[1], 100)
        y_fit  = m * x_fit + b
        ax.plot(x_fit, y_fit,
                color=TEXT_DIM, linewidth=1.0, linestyle="--",
                alpha=0.6, zorder=2, label=f"linear fit  (slope={m:.4f})")

    ax.legend(fontsize=7.5, framealpha=0.35,
              labelcolor=TEXT_WHITE, facecolor=BG_MID,
              edgecolor=SPINE_COL, loc="best")


def _is_nan(v):
    """Safe NaN check that works for both float and numpy scalars."""
    try:
        return np.isnan(float(v))
    except (TypeError, ValueError):
        return False


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Dashboard()
    app.mainloop()
