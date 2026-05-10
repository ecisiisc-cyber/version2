# utils/plot_shmoo.py
# Plotting functions for characterization data.
# Reads the char_data CSV and produces:
#   - Pass/fail shmoo plot
#   - Power shmoo plot (heatmap)
#   - Energy shmoo plot (heatmap)
#   - Multi-variable line plot
#   - BER vs frequency line plot
# All plots are saved as PNG and optionally displayed.

import os
import datetime

try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np
    PLOT_AVAILABLE = True
except ImportError:
    PLOT_AVAILABLE = False
    print("[Plot] matplotlib/pandas/numpy not installed. Plots unavailable.")


def _check():
    if not PLOT_AVAILABLE:
        print("[Plot] Cannot plot: missing matplotlib/pandas/numpy")
        return False
    return True


def _load_csv(csv_path):
    if not os.path.exists(csv_path):
        print(f"[Plot] File not found: {csv_path}")
        return None
    df = pd.read_csv(csv_path)
    # Normalise column names
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def _save_and_show(fig, out_path, show):
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"[Plot] Saved: {out_path}")
    if show:
        plt.show()
    plt.close(fig)


def _shmoo_axes(df):
    """Return sorted unique frequency and voltage arrays."""
    freqs = sorted(df["frequency_hz"].unique())
    volts = sorted(df["voltage_v"].unique())
    return freqs, volts


def _timestamp_suffix():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


# ─────────────────────────────────────────────────────────────────
# 1. Pass / Fail Shmoo
# ─────────────────────────────────────────────────────────────────
def plot_passfail_shmoo(csv_path, out_dir="plots", show=True):
    """
    Plot a pass/fail shmoo.
    CSV must have columns: voltage_v, frequency_hz, pass_fail
    pass_fail column: "pass"/"fail" or 1/0
    Green = pass, Red = fail, Grey = no data
    """
    if not _check():
        return

    df = _load_csv(csv_path)
    if df is None:
        return

    freqs, volts = _shmoo_axes(df)
    grid = np.full((len(volts), len(freqs)), np.nan)

    for _, row in df.iterrows():
        vi = volts.index(row["voltage_v"])
        fi = freqs.index(row["frequency_hz"])
        pf = str(row["pass_fail"]).strip().lower()
        grid[vi, fi] = 1.0 if pf in ("pass", "1", "true") else 0.0

    fig, ax = plt.subplots(figsize=(max(8, len(freqs) * 0.6),
                                    max(5, len(volts) * 0.5)))
    cmap = mcolors.ListedColormap(["#f38ba8", "#a6e3a1"])
    bounds = [-0.5, 0.5, 1.5]
    norm = mcolors.BoundaryNorm(bounds, cmap.N)

    im = ax.imshow(grid, aspect="auto", origin="lower",
                   cmap=cmap, norm=norm,
                   extent=[-0.5, len(freqs) - 0.5,
                           -0.5, len(volts) - 0.5])

    ax.set_xticks(range(len(freqs)))
    ax.set_xticklabels([f"{f/1e6:.2f}" for f in freqs],
                       rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(volts)))
    ax.set_yticklabels([f"{v:.3f}" for v in volts], fontsize=8)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Core Voltage (V)")
    ax.set_title("Pass / Fail Shmoo Plot")

    cbar = fig.colorbar(im, ax=ax, ticks=[0, 1])
    cbar.ax.set_yticklabels(["Fail", "Pass"])

    # Annotate cells
    for vi in range(len(volts)):
        for fi in range(len(freqs)):
            val = grid[vi, fi]
            if not np.isnan(val):
                label = "P" if val == 1 else "F"
                ax.text(fi, vi, label, ha="center", va="center",
                        fontsize=7, fontweight="bold",
                        color="white")

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir,
                       f"shmoo_passfail_{_timestamp_suffix()}.png")
    _save_and_show(fig, out, show)
    return out


# ─────────────────────────────────────────────────────────────────
# 2. Power Shmoo
# ─────────────────────────────────────────────────────────────────
def plot_power_shmoo(csv_path, out_dir="plots", show=True):
    """
    Plot a power shmoo heatmap.
    CSV must have columns: voltage_v, frequency_hz, power_w
    Color intensity = power_w value.
    """
    if not _check():
        return

    df = _load_csv(csv_path)
    if df is None:
        return

    freqs, volts = _shmoo_axes(df)
    grid = np.full((len(volts), len(freqs)), np.nan)

    for _, row in df.iterrows():
        vi = volts.index(row["voltage_v"])
        fi = freqs.index(row["frequency_hz"])
        grid[vi, fi] = float(row.get("power_w", np.nan))

    fig, ax = plt.subplots(figsize=(max(8, len(freqs) * 0.6),
                                    max(5, len(volts) * 0.5)))
    im = ax.imshow(grid, aspect="auto", origin="lower",
                   cmap="viridis",
                   extent=[-0.5, len(freqs) - 0.5,
                           -0.5, len(volts) - 0.5])

    ax.set_xticks(range(len(freqs)))
    ax.set_xticklabels([f"{f/1e6:.2f}" for f in freqs],
                       rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(volts)))
    ax.set_yticklabels([f"{v:.3f}" for v in volts], fontsize=8)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Core Voltage (V)")
    ax.set_title("Power Shmoo Plot")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Power (W)")

    for vi in range(len(volts)):
        for fi in range(len(freqs)):
            val = grid[vi, fi]
            if not np.isnan(val):
                ax.text(fi, vi, f"{val:.3f}", ha="center", va="center",
                        fontsize=6, color="white")

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir,
                       f"shmoo_power_{_timestamp_suffix()}.png")
    _save_and_show(fig, out, show)
    return out


# ─────────────────────────────────────────────────────────────────
# 3. Energy Shmoo
# ─────────────────────────────────────────────────────────────────
def plot_energy_shmoo(csv_path, out_dir="plots", show=True):
    """
    Plot an energy shmoo heatmap.
    CSV must have columns: voltage_v, frequency_hz, energy_j
    Color intensity = energy_j value.
    """
    if not _check():
        return

    df = _load_csv(csv_path)
    if df is None:
        return

    freqs, volts = _shmoo_axes(df)
    grid = np.full((len(volts), len(freqs)), np.nan)

    for _, row in df.iterrows():
        vi = volts.index(row["voltage_v"])
        fi = freqs.index(row["frequency_hz"])
        grid[vi, fi] = float(row.get("energy_j", np.nan))

    fig, ax = plt.subplots(figsize=(max(8, len(freqs) * 0.6),
                                    max(5, len(volts) * 0.5)))
    im = ax.imshow(grid, aspect="auto", origin="lower",
                   cmap="plasma",
                   extent=[-0.5, len(freqs) - 0.5,
                           -0.5, len(volts) - 0.5])

    ax.set_xticks(range(len(freqs)))
    ax.set_xticklabels([f"{f/1e6:.2f}" for f in freqs],
                       rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(volts)))
    ax.set_yticklabels([f"{v:.3f}" for v in volts], fontsize=8)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Core Voltage (V)")
    ax.set_title("Energy Shmoo Plot")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Energy (J)")

    for vi in range(len(volts)):
        for fi in range(len(freqs)):
            val = grid[vi, fi]
            if not np.isnan(val):
                ax.text(fi, vi, f"{val:.4f}", ha="center", va="center",
                        fontsize=6, color="white")

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir,
                       f"shmoo_energy_{_timestamp_suffix()}.png")
    _save_and_show(fig, out, show)
    return out


# ─────────────────────────────────────────────────────────────────
# 4. Multi-variable line plot
# ─────────────────────────────────────────────────────────────────
def plot_multivar(csv_path, x_col, y_cols,
                  threshold=None, threshold_color="red",
                  log_x=False, log_y=False,
                  out_dir="plots", show=True):
    """
    Plot one or more Y columns vs an X column from a CSV.
    x_col      : string, column name for X axis
    y_cols     : list of column name strings for Y axes
    threshold  : optional float — draws a horizontal threshold line
    log_x/log_y: bool — log scale axes
    """
    if not _check():
        return

    df = _load_csv(csv_path)
    if df is None:
        return

    if x_col not in df.columns:
        print(f"[Plot] Column '{x_col}' not found in CSV")
        return

    fig, ax = plt.subplots(figsize=(10, 5))

    for col in y_cols:
        if col in df.columns:
            ax.plot(df[x_col], df[col], marker="o", label=col)
        else:
            print(f"[Plot] Column '{col}' not found, skipping")

    if threshold is not None:
        ax.axhline(y=threshold, color=threshold_color,
                   linestyle="--", linewidth=1.2,
                   label=f"Threshold = {threshold}")

    if log_x:
        ax.set_xscale("log")
    if log_y:
        ax.set_yscale("log")

    ax.set_xlabel(x_col)
    ax.set_ylabel(", ".join(y_cols))
    ax.set_title(f"{', '.join(y_cols)} vs {x_col}")
    ax.legend()
    ax.grid(True, alpha=0.3)

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"lineplot_{_timestamp_suffix()}.png")
    _save_and_show(fig, out, show)
    return out


# ─────────────────────────────────────────────────────────────────
# 5. BER vs Frequency
# ─────────────────────────────────────────────────────────────────
def plot_ber_vs_freq(csv_path, log_y=True,
                     out_dir="plots", show=True):
    """
    Plot BER vs frequency from char data CSV.
    Uses columns: frequency_hz, ber
    log_y=True recommended (BER is usually log-scaled).
    """
    if not _check():
        return

    df = _load_csv(csv_path)
    if df is None:
        return

    if "ber" not in df.columns or "frequency_hz" not in df.columns:
        print("[Plot] CSV must have 'frequency_hz' and 'ber' columns")
        return

    df_plot = df[["frequency_hz", "ber"]].dropna()
    df_plot = df_plot.sort_values("frequency_hz")

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df_plot["frequency_hz"] / 1e6, df_plot["ber"],
            marker="o", color="#7c6af7", linewidth=1.5)

    if log_y:
        ax.set_yscale("log")

    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("BER")
    ax.set_title("BER vs Frequency")
    ax.grid(True, which="both", alpha=0.3)

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir,
                       f"ber_vs_freq_{_timestamp_suffix()}.png")
    _save_and_show(fig, out, show)
    return out


# ─────────────────────────────────────────────────────────────────
# 6. Convenience: plot all shmoos from one CSV
# ─────────────────────────────────────────────────────────────────
def plot_all_shmoos(csv_path, out_dir="plots", show=True):
    """Generate pass/fail, power, and energy shmoo plots from one CSV."""
    paths = []
    for fn in [plot_passfail_shmoo, plot_power_shmoo, plot_energy_shmoo]:
        try:
            p = fn(csv_path, out_dir=out_dir, show=show)
            if p:
                paths.append(p)
        except Exception as e:
            print(f"[Plot] {fn.__name__} failed: {e}")
    return paths
