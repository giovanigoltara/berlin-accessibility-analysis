"""Choropleth maps of the median walk per resident, per LOR Planungsraum.

Reads output/walk_time_by_planungsraum.csv and the LOR geometry; writes
output/maps/plr_median_walk_<mode>.png (one per mode) and
output/maps/plr_median_walk_all_modes.png (small multiples).

All maps share one classed scale so modes can be compared. The five blue
steps were checked with the dataviz palette validator (ordinal mode: one hue,
monotone lightness, visible step gaps, light end >= 2:1 on the surface).
"""
import argparse

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import _bootstrap  # noqa: F401, E402

from berlin_access.config import load_config  # noqa: E402
from berlin_access.pipeline import load_lor, mode_slug, report_modes  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
NO_DATA = "#e6e5e1"
BINS = [0, 5, 10, 15, 30, np.inf]
LABELS = ["5 min or less", "5 to 10", "10 to 15", "15 to 30", "more than 30"]
RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]


def classify(x: pd.Series) -> pd.Series:
    return pd.cut(x, BINS, labels=False, right=True)


def draw(ax, plr, districts, col, label_districts=False):
    ax.set_facecolor(SURFACE)
    nodata = plr[plr[col].isna()]
    data = plr[plr[col].notna()]
    for k, color in enumerate(RAMP):
        part = data[data[col] == k]
        if len(part):
            part.plot(ax=ax, color=color, edgecolor=SURFACE, linewidth=0.25)
    if len(nodata):
        nodata.plot(ax=ax, color=NO_DATA, edgecolor=SURFACE, linewidth=0.25, hatch="////")
    districts.boundary.plot(ax=ax, color=TEXT_2, linewidth=0.7)
    if label_districts:
        for _, r in districts.iterrows():
            p = r.geometry.representative_point()
            ax.annotate(
                r["district"].replace("-", "-\n"), (p.x, p.y), ha="center", va="center", fontsize=7, color=TEXT,
                path_effects=[patheffects.withStroke(linewidth=2.5, foreground=SURFACE)],
            )
    ax.set_axis_off()


def legend_handles(n_low):
    h = [Patch(facecolor=c, edgecolor="none", label=lbl) for c, lbl in zip(RAMP, LABELS)]
    h.append(Patch(facecolor=NO_DATA, edgecolor=TEXT_2, linewidth=0.3, hatch="////",
                   label=f"fewer than 100 residents ({n_low})"))
    return h


def main(cfg) -> None:
    out = cfg.path("output")
    maps_dir = out / "maps"
    maps_dir.mkdir(exist_ok=True)
    v = cfg["walk_speed_main_mps"]
    modes = report_modes(cfg)
    limit = "stops inside Berlin only" if cfg["stop_buffer_m"] == 0 else f"stops up to {cfg['stop_buffer_m']} m outside Berlin"

    lor = load_lor(cfg.path("lor"), cfg["crs"])
    districts = lor.dissolve("district").reset_index()[["district", "geometry"]]
    s = pd.read_csv(out / "walk_time_by_planungsraum.csv", dtype={"unit_id": str})
    s = s[(s["weighting"] == "residents") & (s["speed_mps"] == v) & (s["unit_id"] != "Berlin")]
    low = s.drop_duplicates("unit_id").set_index("unit_id")["low_population"]
    wide = s.pivot(index="unit_id", columns="mode", values="median_min")
    plr = lor.merge(wide, left_on="plr_id", right_index=True, how="left")
    is_low = plr["plr_id"].map(low).fillna(True).astype(bool)
    n_low = int(is_low.sum())
    for m in modes:
        plr[f"cls_{m}"] = classify(plr[m]).where(~is_low)

    source = (f"Median walk per resident to the nearest stop, LOR Planungsräume, {v} m/s, {limit}. "
              "Data: OSM (ODbL), VBB GTFS, LOR 2021, Einwohnerregister 31.12.2025.")

    for m in modes:
        fig, ax = plt.subplots(figsize=(10, 7), dpi=150, facecolor=SURFACE)
        draw(ax, plr, districts, f"cls_{m}", label_districts=True)
        ax.set_title(f"Walk to the nearest {m} stop", loc="left", fontsize=13, color=TEXT, pad=10)
        ax.legend(handles=legend_handles(n_low), loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False,
                  fontsize=9, title="Median walk per resident", title_fontsize=9, labelcolor=TEXT_2,
                  alignment="left")
        fig.text(0.02, 0.015, source, fontsize=6.5, color=TEXT_2, wrap=True)
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        fig.savefig(maps_dir / f"plr_median_walk_{mode_slug(m)}.png", facecolor=SURFACE)
        plt.close(fig)

    ncols = 3
    nrows = -(-len(modes) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(13, 4.3 * nrows + 0.9), dpi=150, facecolor=SURFACE)
    for ax in axes.flat:
        ax.set_axis_off()
    for ax, m in zip(axes.flat, modes):
        draw(ax, plr, districts, f"cls_{m}")
        ax.set_title(m, loc="left", fontsize=11, color=TEXT)
    fig.legend(handles=legend_handles(n_low), loc="lower center", bbox_to_anchor=(0.5, 0.03), ncol=6,
               frameon=False, fontsize=9, labelcolor=TEXT_2, title="Median walk per resident", title_fontsize=9)
    fig.suptitle("Walk to the nearest stop by mode, per Planungsraum", x=0.01, ha="left", fontsize=14, color=TEXT)
    fig.text(0.01, 0.008, source, fontsize=7, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.09, 1, 0.97))
    fig.savefig(maps_dir / "plr_median_walk_all_modes.png", facecolor=SURFACE)
    plt.close(fig)
    print(f"maps written to {maps_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    main(load_config(ap.parse_args().config))
