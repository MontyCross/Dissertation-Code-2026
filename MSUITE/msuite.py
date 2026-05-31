"""
msuite.py  —  MSuite: Metallographic Analysis Launcher
=======================================================
Central launcher for the LOM point-counting and grain-size
measurement toolkit.

Modes:
    python msuite.py          → Normal mode (all saves go to real results)
    python msuite.py --demo   → Demo mode  (saves redirected to temp dirs)

Tools launched:
    • LOM Point Counter   (lom_score.py)
    • Grain Intercept     (grain_intercept.py)
    • LOM Analyser        (lom_analyse.py)     — standalone
    • Grain Analyser      (grain_analyse.py)    — standalone
    • Results Dashboard   (lom_dashboard.py)
"""

import sys
import os
import subprocess
import shutil
import tempfile
import tkinter as tk
from tkinter import font as tkfont, messagebox

# ── Resolve script directory (all tools live alongside this file) ─────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEMO_MODE = "--demo" in sys.argv

# Fixed demo root — all demo outputs go here; "wipe" deletes this folder
DEMO_ROOT = os.path.join(tempfile.gettempdir(), "msuite_demo")

# ── Colour palette (matches dashboard dark theme) ────────────────────────────
BG_DARK    = "#121212"
BG_MID     = "#1E1E1E"
BG_CARD    = "#252525"
BG_HOVER   = "#2F2F2F"
TEXT_WHITE  = "#ECEFF1"
TEXT_DIM    = "#90A4AE"
ACCENT      = "#4FC3F7"     # light blue
ACCENT_WARN = "#FFB74D"     # amber — demo mode indicator
BORDER      = "#37474F"
BTN_BG      = "#263238"
BTN_HOVER   = "#37474F"
BTN_ACTIVE  = "#455A64"


# ═════════════════════════════════════════════════════════════════════════════
#  LAUNCHER
# ═════════════════════════════════════════════════════════════════════════════

class MSuiteLauncher(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("MSuite — Metallographic Analysis" +
                   ("  [DEMO]" if DEMO_MODE else ""))
        self.configure(bg=BG_DARK)
        self.resizable(False, False)

        # ── Fonts ─────────────────────────────────────────────────────────
        self._fn_title   = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        self._fn_sub     = tkfont.Font(family="Segoe UI", size=10)
        self._fn_btn     = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self._fn_desc    = tkfont.Font(family="Segoe UI", size=9)
        self._fn_section = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self._fn_footer  = tkfont.Font(family="Segoe UI", size=8)

        self._build_ui()
        self._centre_window()

    # ── Layout ────────────────────────────────────────────────────────────

    def _build_ui(self):
        pad = 24

        # ── Title block ───────────────────────────────────────────────────
        title_frame = tk.Frame(self, bg=BG_DARK)
        title_frame.pack(fill="x", padx=pad, pady=(pad, 4))

        tk.Label(
            title_frame, text="MSuite", font=self._fn_title,
            fg=ACCENT, bg=BG_DARK, anchor="w",
        ).pack(side="left")

        if DEMO_MODE:
            tk.Label(
                title_frame, text="  DEMO", font=self._fn_sub,
                fg=BG_DARK, bg=ACCENT_WARN, anchor="w",
                padx=6, pady=1,
            ).pack(side="left", padx=(10, 0))

        tk.Label(
            self, text="Metallographic analysis toolkit",
            font=self._fn_sub, fg=TEXT_DIM, bg=BG_DARK, anchor="w",
        ).pack(fill="x", padx=pad, pady=(0, 4))

        if DEMO_MODE:
            tk.Label(
                self,
                text="Demo mode — all outputs go to temporary directories.  "
                     "Your results data is safe.",
                font=self._fn_desc, fg=ACCENT_WARN, bg=BG_DARK, anchor="w",
            ).pack(fill="x", padx=pad, pady=(0, 12))
        else:
            tk.Frame(self, bg=BG_DARK, height=8).pack()

        # ── Separator ─────────────────────────────────────────────────────
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=pad)

        # ── Primary tools section ─────────────────────────────────────────
        tk.Label(
            self, text="MEASUREMENT TOOLS", font=self._fn_section,
            fg=TEXT_DIM, bg=BG_DARK, anchor="w",
        ).pack(fill="x", padx=pad, pady=(14, 6))

        self._tool_button(
            label="LOM Point Counter",
            desc="Interactive point-counting for DP area fraction (ASTM E562)",
            script="lom_score.py",
        )
        self._tool_button(
            label="Grain Size — Intercept",
            desc="Linear / circular intercept grain-size measurement",
            script="grain_intercept.py",
        )

        # ── Analysis section ──────────────────────────────────────────────
        tk.Frame(self, bg=BG_DARK, height=6).pack()
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=pad)
        tk.Label(
            self, text="ANALYSIS  (standalone)", font=self._fn_section,
            fg=TEXT_DIM, bg=BG_DARK, anchor="w",
        ).pack(fill="x", padx=pad, pady=(14, 6))

        self._tool_button(
            label="LOM Analyser",
            desc="Vv computation from a scored CSV — pick file manually",
            script="lom_analyse.py",
        )
        self._tool_button(
            label="Grain Analyser",
            desc="Grain-size analysis from an intercept summary CSV",
            script="grain_analyse.py",
        )

        # ── Dashboard section ─────────────────────────────────────────────
        tk.Frame(self, bg=BG_DARK, height=6).pack()
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=pad)
        tk.Label(
            self, text="RESULTS", font=self._fn_section,
            fg=TEXT_DIM, bg=BG_DARK, anchor="w",
        ).pack(fill="x", padx=pad, pady=(14, 6))

        self._tool_button(
            label="Results Dashboard",
            desc="Interactive dashboard — Vv curves, grain size, comparisons",
            script="lom_dashboard.py",
            demo_flag=False,      # dashboard runs unchanged
        )

        # ── Footer ────────────────────────────────────────────────────────
        tk.Frame(self, bg=BG_DARK, height=10).pack()
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=pad)

        if DEMO_MODE:
            wipe_frame = tk.Frame(self, bg=BG_DARK)
            wipe_frame.pack(fill="x", padx=pad, pady=(10, 0))

            self._wipe_btn = tk.Button(
                wipe_frame, text="Clear Demo Data",
                font=self._fn_desc, fg=TEXT_WHITE, bg="#4E342E",
                activebackground="#6D4C41", activeforeground=TEXT_WHITE,
                relief="flat", cursor="hand2", padx=10, pady=4,
                command=self._wipe_demo_data,
            )
            self._wipe_btn.pack(side="left")

            self._wipe_status = tk.Label(
                wipe_frame, text="", font=self._fn_footer,
                fg=TEXT_DIM, bg=BG_DARK, anchor="w",
            )
            self._wipe_status.pack(side="left", padx=(10, 0))

            self._update_wipe_status()

        tk.Label(
            self,
            text="Discontinuous precipitation in AZ91 / AZ80 Mg–Al alloys",
            font=self._fn_footer, fg=TEXT_DIM, bg=BG_DARK,
        ).pack(pady=(10, pad))

    # ── Button factory ────────────────────────────────────────────────────

    def _tool_button(self, label, desc, script, demo_flag=True):
        """Create a styled launcher button with description text."""

        frame = tk.Frame(self, bg=BG_CARD, highlightbackground=BORDER,
                         highlightthickness=1, cursor="hand2")
        frame.pack(fill="x", padx=24, pady=3)

        inner = tk.Frame(frame, bg=BG_CARD)
        inner.pack(fill="x", padx=14, pady=10)

        lbl = tk.Label(inner, text=label, font=self._fn_btn,
                       fg=TEXT_WHITE, bg=BG_CARD, anchor="w")
        lbl.pack(fill="x")

        dlbl = tk.Label(inner, text=desc, font=self._fn_desc,
                        fg=TEXT_DIM, bg=BG_CARD, anchor="w")
        dlbl.pack(fill="x", pady=(2, 0))

        # Bind click to entire card
        cmd = lambda e, s=script, d=demo_flag: self._launch(s, d)
        for widget in (frame, inner, lbl, dlbl):
            widget.bind("<Button-1>", cmd)
            widget.bind("<Enter>",
                        lambda e, f=frame, i=inner, l=lbl, d_=dlbl:
                            self._hover(f, i, l, d_, True))
            widget.bind("<Leave>",
                        lambda e, f=frame, i=inner, l=lbl, d_=dlbl:
                            self._hover(f, i, l, d_, False))

    def _hover(self, frame, inner, lbl, dlbl, entering):
        bg = BG_HOVER if entering else BG_CARD
        for w in (frame, inner, lbl, dlbl):
            w.configure(bg=bg)

    # ── Launch handler ────────────────────────────────────────────────────

    def _launch(self, script, pass_demo=True):
        path = os.path.join(SCRIPT_DIR, script)
        if not os.path.isfile(path):
            messagebox.showerror(
                "Script not found",
                f"Cannot find:\n{path}\n\n"
                f"Ensure {script} is in the same folder as msuite.py.",
                parent=self,
            )
            return

        cmd = [sys.executable, path]
        if DEMO_MODE and pass_demo:
            cmd.append("--demo")

        print(f"[MSuite] Launching: {' '.join(cmd)}")
        subprocess.Popen(cmd)

    # ── Demo data management ──────────────────────────────────────────────

    def _wipe_demo_data(self):
        if not os.path.isdir(DEMO_ROOT):
            messagebox.showinfo("Nothing to clear",
                                "Demo data folder does not exist yet.",
                                parent=self)
            return

        confirmed = messagebox.askyesno(
            "Clear Demo Data",
            f"Delete all demo outputs?\n\n{DEMO_ROOT}\n\n"
            f"This resets repeat counters to r1 for the next demo run.",
            parent=self,
        )
        if not confirmed:
            return

        try:
            shutil.rmtree(DEMO_ROOT)
            print(f"[MSuite] Wiped demo data → {DEMO_ROOT}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not delete:\n{e}",
                                 parent=self)
            return

        self._update_wipe_status()

    def _update_wipe_status(self):
        if not os.path.isdir(DEMO_ROOT):
            self._wipe_status.configure(text="No demo data", fg=TEXT_DIM)
            return
        # Count files recursively
        n = sum(len(files) for _, _, files in os.walk(DEMO_ROOT))
        self._wipe_status.configure(
            text=f"{n} file{'s' if n != 1 else ''} in demo folder",
            fg=ACCENT_WARN if n > 0 else TEXT_DIM,
        )

    # ── Centre on screen ──────────────────────────────────────────────────

    def _centre_window(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mode_str = "DEMO" if DEMO_MODE else "NORMAL"
    print(f"[MSuite] Starting in {mode_str} mode")
    print(f"[MSuite] Script dir: {SCRIPT_DIR}")
    app = MSuiteLauncher()
    app.mainloop()
