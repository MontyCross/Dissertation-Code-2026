# Dissertation-Code-2026
# MSuite: Metallographic Analysis Toolkit
**Master's Dissertation Code Repository — AZ91 / AZ80 Magnesium Alloy Analysis**

This repository contains **MSuite**, a custom-built Python stereological analysis toolkit used to measure Discontinuous Precipitate (DP) area fractions (Vv) and ASTM grain sizes via interactive point-counting and intercept methods. 

## 1. Overview of Tools
The suite consists of a central launcher (`msuite.py`) and several modular scripts:
* **LOM Point Counter (`lom_score.py`):** Interactive grid point-counting (ASTM E562) for DP area fraction.
* **LOM Analyser (`lom_analyse.py`):** Computes Vv from scored point-count data.
* **Grain Intercept (`grain_intercept.py`):** Interactive linear (Heyn) and circular (Abrams) intercept counting (ASTM E112).
* **Grain Analyser (`grain_analyse.py`):** Computes ASTM grain size number (G) and mean lineal intercept (l).
* **Results Dashboard (`lom_dashboard.py`):** Generates aggregated plots, uncertainty analysis, and casting method comparisons.

## 2. Requirements
This codebase requires **Python 3.8+**. The following external libraries must be installed:

    pip install numpy pandas matplotlib pillow

*Note: The UI relies on `tkinter`, which is included in standard Python distributions.*

## 3. Critical Setup: Folder Structure & `BASE_DIR`
To ensure blind-marking anonymity and cross-platform compatibility, this code uses absolute paths anchored by a single user-defined `BASE_DIR` variable. 

**Before running the code, you must update the `BASE_DIR` variable at the top of the following files:**
* `grain_analyse.py`
* `grain_intercept.py`
* `lom_analyse.py`
* `lom_dashboard.py`
* `lom_score.py`

Change the `BASE_DIR` path to point to the root folder where you have extracted the dataset on your local machine.

### Expected Directory Tree
The dataset must be extracted so that the directories match the exact structure below relative to your `BASE_DIR`:

    [Your BASE_DIR path] / Magnesium Masters Project
      ├── ANALYSED/
      │   └── Etched/
      │       ├── D/               # Direct Chill Cast (DCC)
      │       │   └── DC/
      │       │       └── DC19/
      │       │           └── 10x af.png
      │       ├── G/               # Gravity Cast (GC)
      │       └── H/               # High-Pressure Die Cast (HPDC)
      ├── RESULTS/                 # (Generated automatically) LOM point-count CSVs
      ├── RESULTS_GRAIN_SIZE/      # (Generated automatically) Grain intercept CSVs
      └── RESULTS_PLOTS/           # (Generated automatically) Output graphs from dashboard

*Note: All Python scripts (`*.py`) should remain together in their downloaded folder and do not need to be placed inside the data directory.*

## 4. How to Run
Once dependencies are installed and the `BASE_DIR` is set, launch the central interface via the command line:

    python msuite.py

### Demo Mode (Safe Testing)
If you wish to test the scoring and intercept tools without writing files to the permanent `RESULTS` directories, launch the suite in demo mode:

    python msuite.py --demo

In demo mode, all output CSVs are redirected to a temporary system directory, ensuring the original dataset remains pristine. You can clear the demo data at any time using the "Clear Demo Data" button in the MSuite interface.
