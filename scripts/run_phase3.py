"""Phase 3: metric access to transit versus configurational centrality.

Per residential building: walk time to transit (Phase 0) and the Space Syntax
measures of its nearest street segment (Phase 1, citywide run). Writes

  output/phase3/correlations.csv               Spearman per district, building and Planungsraum level
  output/phase3/divergence_by_planungsraum.csv  walk time / integration thirds and divergence class
  output/phase3/reach_vs_centrality_<pilot>.csv Phase 2 reach vs centrality (pilot district)
  output/phase3/summary.json
  output/maps/phase3_divergence.png

Requires run_accessibility.py, run_segments.py --district Berlin and run_pst_inputs.py.
"""
import json

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

import _bootstrap  # noqa: F401, E402

from berlin_access.config import load_config  # noqa: E402
from berlin_access.pipeline import load_lor, weighted_quantiles  # noqa: E402

PILOT = "Friedrichshain-Kreuzberg"
TRANSIT = {  # label -> Phase 0 distance column
    "walk_su_min": "dist_m_S- or U-Bahn",
    "walk_frequent_any_min": "dist_m_Any mode_frequent_10min",
}
MEASURES = ["nain_800", "nain_2000", "nach_800", "nach_2000", "cc_harmonic_800"]
LABELS = {"nain_800": "NAIN 800 m", "nain_2000": "NAIN 2000 m", "nach_800": "NACH 800 m",
          "nach_2000": "NACH 2000 m", "cc_harmonic_800": "metric closeness 800 m"}
DIVERGENCE_MEASURE = "nain_2000"

SURFACE, TEXT, TEXT_2 = "#fcfcfb", "#0b0b0b", "#52514e"
CLASS_COLORS = {
    "close to transit, segregated": "#eb6834",   # categorical slot 2
    "far from transit, integrated": "#2a78d6",   # categorical slot 1
    "concordant": "#c9c8c2",
    "middle": "#ecebe7",
}


def wmedian(x, w):
    ok = np.isfinite(x) & (w > 0)
    return weighted_quantiles(x[ok], w[ok], [0.5])[0] if ok.any() else np.nan


def spearman(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return np.nan, int(ok.sum())
    return float(spearmanr(x[ok], y[ok]).statistic), int(ok.sum())


def main():
    cfg = load_config()
    out, der = cfg.path("output"), cfg.path("derived")
    p3 = out / "phase3"
    p3.mkdir(parents=True, exist_ok=True)
    crs = cfg["crs"]
    v = cfg["walk_speed_main_mps"]
    min_res = cfg["min_unit_residents"]
    meta = {"walk_speed_mps": v, "divergence_measure": DIVERGENCE_MEASURE}

    b = gpd.read_parquet(der / "building_walk_dist.parquet").to_crs(crs)
    b = b[b["residents"] > 0].reset_index(drop=True)
    for lab, col in TRANSIT.items():
        b[lab] = b[col] / v / 60.0

    seg = gpd.read_file(out / "segments_berlin.gpkg", columns=MEASURES + ["live", "street"])
    seg = seg[seg["live"].astype(bool)].reset_index(drop=True)
    j = gpd.sjoin_nearest(b[["geometry"]], seg[MEASURES + ["street", "geometry"]], how="left", distance_col="seg_dist_m")
    j = j[~j.index.duplicated(keep="first")]
    for c in MEASURES + ["street", "seg_dist_m"]:
        b[c] = j[c].to_numpy()
    meta["buildings"] = int(len(b))
    meta["median_distance_to_segment_m"] = round(float(b["seg_dist_m"].median()), 1)
    b.drop(columns="geometry").to_parquet(der / "phase3_buildings.parquet")

    # Correlations per district: building level (unweighted) and Planungsraum
    # level (resident-weighted medians, Planungsräume with >= min_res residents).
    plr = []
    for pid, g in b.groupby("plr_id"):
        w = g["residents"].to_numpy()
        row = {"plr_id": pid, "district": g["district"].iloc[0], "residents": float(w.sum())}
        for c in list(TRANSIT) + MEASURES:
            row[c] = wmedian(g[c].to_numpy(float), w)
        plr.append(row)
    plr = pd.DataFrame(plr)
    plr = plr[plr["residents"] >= min_res].reset_index(drop=True)

    rows = []
    for district in ["Berlin"] + sorted(b["district"].unique()):
        gb = b if district == "Berlin" else b[b["district"] == district]
        gp = plr if district == "Berlin" else plr[plr["district"] == district]
        for t in TRANSIT:
            for m in MEASURES:
                rb, nb = spearman(gb[t].to_numpy(float), gb[m].to_numpy(float))
                rp, npl = spearman(gp[t].to_numpy(float), gp[m].to_numpy(float))
                rows.append({"district": district, "transit": t, "measure": m,
                             "rho_buildings": round(rb, 3), "n_buildings": nb,
                             "rho_planungsraeume": round(rp, 3) if np.isfinite(rp) else None, "n_planungsraeume": npl})
    corr = pd.DataFrame(rows)
    corr.to_csv(p3 / "correlations.csv", index=False)

    # Divergence: citywide thirds of Planungsräume on walk time to S/U and on NAIN 2000.
    t_q = plr["walk_su_min"].quantile([1 / 3, 2 / 3]).to_numpy()
    m_q = plr[DIVERGENCE_MEASURE].quantile([1 / 3, 2 / 3]).to_numpy()
    plr["transit_third"] = np.select([plr["walk_su_min"] <= t_q[0], plr["walk_su_min"] > t_q[1]], ["close", "far"], "middle")
    plr["integration_third"] = np.select([plr[DIVERGENCE_MEASURE] >= m_q[1], plr[DIVERGENCE_MEASURE] < m_q[0]],
                                         ["integrated", "segregated"], "middle")
    cls = np.full(len(plr), "middle", dtype=object)
    cls[(plr["transit_third"] == "close") & (plr["integration_third"] == "segregated")] = "close to transit, segregated"
    cls[(plr["transit_third"] == "far") & (plr["integration_third"] == "integrated")] = "far from transit, integrated"
    conc = ((plr["transit_third"] == "close") & (plr["integration_third"] == "integrated")) | \
           ((plr["transit_third"] == "far") & (plr["integration_third"] == "segregated"))
    cls[conc.to_numpy()] = "concordant"
    plr["divergence"] = cls
    lor = load_lor(cfg.path("lor"), crs)
    plr = plr.merge(lor[["plr_id", "plr_name"]], on="plr_id", how="left")
    plr.round(4).to_csv(p3 / "divergence_by_planungsraum.csv", index=False)
    meta["thirds"] = {"walk_su_min": [round(x, 2) for x in t_q], DIVERGENCE_MEASURE: [round(x, 4) for x in m_q]}
    meta["planungsraeume_by_class"] = plr["divergence"].value_counts().to_dict()
    meta["residents_by_class"] = plr.groupby("divergence")["residents"].sum().round(0).to_dict()

    # Phase 2 reach (pilot) against centrality, building level.
    reach = pd.read_csv(out / "pst" / f"python_reach_{PILOT.lower()}.csv")
    rb = b[["osm_id"] + MEASURES].merge(reach[["osm_id", "reach_su_800", "reach_anyf_400"]], on="osm_id")
    rr = []
    for rcol in ("reach_su_800", "reach_anyf_400"):
        for m in MEASURES:
            r_, n_ = spearman(rb[rcol].to_numpy(float), rb[m].to_numpy(float))
            rr.append({"reach": rcol, "measure": m, "rho": round(r_, 3), "n_buildings": n_})
    pd.DataFrame(rr).to_csv(p3 / f"reach_vs_centrality_{PILOT.lower()}.csv", index=False)

    # Map of divergence classes per Planungsraum.
    g = lor.merge(plr[["plr_id", "divergence"]], on="plr_id", how="left")
    districts = lor.dissolve("district").reset_index()
    fig, ax = plt.subplots(figsize=(12, 9), dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for c, col in CLASS_COLORS.items():
        part = g[g["divergence"] == c]
        if len(part):
            part.plot(ax=ax, color=col, edgecolor=SURFACE, linewidth=0.3)
    nod = g[g["divergence"].isna()]
    if len(nod):
        nod.plot(ax=ax, color=SURFACE, edgecolor="#bdbcb6", linewidth=0.3, hatch="////")
    districts.boundary.plot(ax=ax, color=TEXT_2, linewidth=0.7)
    ax.set_axis_off()
    counts = plr["divergence"].value_counts()
    handles = [Patch(facecolor=col, edgecolor="none", label=f"{c} ({counts.get(c, 0)})") for c, col in CLASS_COLORS.items()]
    handles.append(Patch(facecolor=SURFACE, edgecolor="#bdbcb6", hatch="////", label=f"fewer than {min_res} residents"))
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=9,
              labelcolor=TEXT_2, title="Planungsräume (count)", title_fontsize=9, alignment="left")
    ax.set_title("Where access to rail and street-network integration diverge", loc="left", fontsize=13, color=TEXT)
    fig.text(0.01, 0.015,
             "Thirds over all Planungsräume of the resident-weighted median walk to the nearest S- or U-Bahn station "
             f"({v} m/s) and of the median NAIN at 2000 m of residents' nearest street. 'Concordant' = close & integrated "
             "or far & segregated. Data: OSM (ODbL), VBB GTFS, LOR 2021, Einwohnerregister 31.12.2025.",
             fontsize=7, color=TEXT_2, wrap=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out / "maps" / "phase3_divergence.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)

    (p3 / "summary.json").write_text(json.dumps(meta, indent=2, default=str, ensure_ascii=False))
    print(json.dumps(meta, indent=2, default=str, ensure_ascii=False))
    print(corr[corr["district"] == "Berlin"].to_string(index=False))


if __name__ == "__main__":
    main()
