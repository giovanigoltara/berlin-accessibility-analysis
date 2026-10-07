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
CIRCLE = "#eb6834"  # second hue, distinct from the blue ramp
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


def plr_classes(out, lor, csv_name, weighting, speed, modes):
    """Planungsräume with the class of the median walk per mode; low-population units unclassed."""
    s = pd.read_csv(out / csv_name, dtype={"unit_id": str})
    s = s[(s["weighting"] == weighting) & (s["speed_mps"] == speed) & (s["unit_id"] != "Berlin")]
    low = s.drop_duplicates("unit_id").set_index("unit_id")["low_population"]
    wide = s.pivot(index="unit_id", columns="mode", values="median_min")
    plr = lor.merge(wide, left_on="plr_id", right_index=True, how="left")
    is_low = plr["plr_id"].map(low).fillna(True).astype(bool)
    for m in modes:
        plr[f"cls_{m}"] = classify(plr[m]).where(~is_low)
    return plr, int(is_low.sum()), s


def single_map(plr, districts, col, title, n_low, source, path, legend_title="Median walk per resident"):
    fig, ax = plt.subplots(figsize=(10, 7), dpi=150, facecolor=SURFACE)
    draw(ax, plr, districts, col, label_districts=True)
    ax.set_title(title, loc="left", fontsize=13, color=TEXT, pad=10)
    ax.legend(handles=legend_handles(n_low), loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False,
              fontsize=9, title=legend_title, title_fontsize=9, labelcolor=TEXT_2, alignment="left")
    fig.text(0.02, 0.015, source, fontsize=6.5, color=TEXT_2, wrap=True)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def overview_map(plr, districts, modes, title, n_low, source, path):
    ncols = 3
    nrows = -(-len(modes) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(13, 4.3 * nrows + 0.9), dpi=150, facecolor=SURFACE)
    for ax in axes.flat:
        ax.set_axis_off()
    for ax, m in zip(axes.flat, modes):
        draw(ax, plr, districts, f"cls_{m}")
        ax.set_title(m, loc="left", fontsize=11, color=TEXT)
    fig.legend(handles=legend_handles(n_low), loc="lower center", bbox_to_anchor=(0.5, 0.03 / nrows * 3), ncol=6,
               frameon=False, fontsize=9, labelcolor=TEXT_2, title="Median walk per resident", title_fontsize=9)
    fig.suptitle(title, x=0.01, ha="left", fontsize=14, color=TEXT)
    fig.text(0.01, 0.008, source, fontsize=7, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.09 / nrows * 3, 1, 0.97))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def older_map(out, lor, districts, mode, n_low_all, path, data_note):
    """Left: median walk per resident 65+ at 1.0 m/s. Right: how many residents 65+
    are beyond 15 min, as circles sized by count (area), so large units are not
    over-emphasised as they would be in a filled map of counts."""
    plr, n_low, s = plr_classes(out, lor, "walk_time_by_planungsraum.csv", "residents_65plus", 1.0, [mode])
    g = s[s["mode"] == mode].set_index("unit_id")
    count = (g["share_over_15min"] * g["residents"]).where(~g["low_population"])
    plr["n_over_15"] = plr["plr_id"].map(count)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 8), dpi=150, facecolor=SURFACE)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.86, bottom=0.17, wspace=0.04)
    draw(a1, plr, districts, f"cls_{mode}")
    a1.set_title(f"Median walk to the nearest {mode} stop\nper resident 65+, at 1.0 m/s", loc="left", fontsize=11,
                 color=TEXT, pad=8)

    a2.set_facecolor(SURFACE)
    plr.plot(ax=a2, color="#ebeae6", edgecolor=SURFACE, linewidth=0.25)
    districts.boundary.plot(ax=a2, color=TEXT_2, linewidth=0.7)
    pts = plr[plr["n_over_15"] > 0].copy()
    pts["geometry"] = pts.geometry.representative_point()
    scale = 0.06  # marker area (pt^2) per person
    a2.scatter(pts.geometry.x, pts.geometry.y, s=pts["n_over_15"] * scale, color=CIRCLE, alpha=0.7,
               edgecolor=SURFACE, linewidth=0.6, zorder=3)
    a2.set_axis_off()
    total = count.sum()
    a2.set_title(f"Residents 65+ more than 15 min on foot (1.0 m/s) from an {mode} stop:\n"
                 f"{total:,.0f} people. One circle per Planungsraum, area = number of people", loc="left",
                 fontsize=11, color=TEXT, pad=8)
    fig.suptitle("Older residents and rapid transit, per Planungsraum", x=0.01, y=0.97, ha="left", fontsize=14, color=TEXT)

    fig.legend(handles=legend_handles(n_low), loc="lower center", bbox_to_anchor=(0.25, 0.05), ncol=3,
               frameon=False, fontsize=8, labelcolor=TEXT_2, title="Median walk per resident 65+", title_fontsize=8)
    sizes = [500, 2000, 5000]
    handles = [plt.scatter([], [], s=n * scale, color=CIRCLE, alpha=0.7, edgecolor=SURFACE, label=f"{n:,}") for n in sizes]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.75, 0.05), ncol=3, frameon=False, fontsize=8,
               labelcolor=TEXT_2, title="Residents 65+ beyond 15 min", title_fontsize=8, columnspacing=2.5)
    fig.text(0.01, 0.012, data_note, fontsize=7, color=TEXT_2)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main(cfg) -> None:
    out = cfg.path("output")
    maps_dir = out / "maps"
    maps_dir.mkdir(exist_ok=True)
    v = cfg["walk_speed_main_mps"]
    modes = report_modes(cfg)
    limit = "stops inside Berlin only" if cfg["stop_buffer_m"] == 0 else f"stops up to {cfg['stop_buffer_m']} m outside Berlin"
    data = "Data: OSM (ODbL), VBB GTFS, LOR 2021, Einwohnerregister 31.12.2025."

    lor = load_lor(cfg.path("lor"), cfg["crs"])
    districts = lor.dissolve("district").reset_index()[["district", "geometry"]]

    plr, n_low, _ = plr_classes(out, lor, "walk_time_by_planungsraum.csv", "residents", v, modes)
    source = f"Median walk per resident to the nearest stop, LOR Planungsräume, {v} m/s, {limit}. {data}"
    for m in modes:
        single_map(plr, districts, f"cls_{m}", f"Walk to the nearest {m} stop", n_low, source,
                   maps_dir / f"plr_median_walk_{mode_slug(m)}.png")
    overview_map(plr, districts, modes, "Walk to the nearest stop by mode, per Planungsraum", n_low, source,
                 maps_dir / "plr_median_walk_all_modes.png")

    fq = cfg.raw.get("frequency")
    if fq:
        tag = f"frequent_{fq['max_headway_min']}min"
        csv = f"walk_time_by_planungsraum_{tag}.csv"
        if (out / csv).exists():
            plr_f, n_low_f, _ = plr_classes(out, lor, csv, "residents", v, modes)
            day = pd.Timestamp(str(fq["date"])).strftime("%a %d %b %Y")
            rule = f"departure at least every {fq['max_headway_min']} min, {fq['window'][0]}-{fq['window'][1]} on {day}"
            src_f = f"Median walk per resident to the nearest frequent stop ({rule}), {v} m/s, {limit}. {data}"
            for m in modes:
                single_map(plr_f, districts, f"cls_{m}", f"Walk to the nearest frequent {m} stop", n_low_f, src_f,
                           maps_dir / f"plr_{tag}_median_walk_{mode_slug(m)}.png")
            overview_map(plr_f, districts, modes, f"Walk to the nearest frequent stop ({rule})", n_low_f, src_f,
                         maps_dir / f"plr_{tag}_median_walk_all_modes.png")

    older_map(out, lor, districts, "S- or U-Bahn", n_low, maps_dir / "plr_older_residents_S-or-U-Bahn.png",
              f"Residents 65+ per Planungsraum (Einwohnerregister 31.12.2025), spread within the Planungsraum like all "
              f"residents. Walking speed 1.0 m/s, {limit}. {data}")
    print(f"maps written to {maps_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    main(load_config(ap.parse_args().config))
