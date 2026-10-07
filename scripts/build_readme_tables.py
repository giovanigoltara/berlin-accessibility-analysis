"""Regenerate the results section of README.md from output/*.csv.

Everything between the GENERATED markers is overwritten. If the pipeline has
not been run, the section says so and contains no numbers.
"""
import argparse
import json
import re

import pandas as pd

import _bootstrap  # noqa: F401

from berlin_access.config import load_config
from berlin_access.pipeline import report_modes

BEGIN = "<!-- BEGIN GENERATED: results (scripts/build_readme_tables.py) -->"
END = "<!-- END GENERATED: results -->"


def fmt(x, pct=False, signed=False):
    if pd.isna(x):
        return "n/a"
    if pct:
        return f"{100 * x:.1f}%"
    if signed:
        return "0.0" if abs(x) < 0.05 else f"{x:+.1f}"
    return f"{x:.1f}"


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def build(cfg) -> str:
    out = cfg.path("output")
    csv = out / "walk_time_by_district.csv"
    if not csv.exists():
        return (
            "_Results have not been generated yet. Run `python scripts/run_accessibility.py` and then "
            "`python scripts/build_readme_tables.py`._"
        )
    s = pd.read_csv(csv)
    modes = report_modes(cfg)
    v = cfg["walk_speed_main_mps"]
    buf = cfg["stop_buffer_m"]
    meta = json.loads((out / "run_metadata.json").read_text()) if (out / "run_metadata.json").exists() else {}
    order = ["Berlin"] + sorted(d for d in s["unit_id"].unique() if d != "Berlin")
    limit = "only stops inside Berlin" if buf == 0 else f"stops up to {buf} m outside Berlin"
    key = ["unit_id", "mode", "speed_mps"]

    def wide(df, col, **kw):
        w = df[df["speed_mps"] == v].pivot(index="unit_id", columns="mode", values=col)
        w = w.reindex(index=order, columns=modes).apply(lambda c: c.map(lambda x: fmt(x, **kw)))
        return w.reset_index().rename(columns={"unit_id": "District"})

    res = s[s["weighting"] == "residents"]
    bld = s[s["weighting"] == "buildings"]
    parts = [
        f"All tables: walking speed {v} m/s, {limit}, residents allocated to buildings "
        "(see `docs/methods.md`) unless stated otherwise."
    ]
    parts.append("#### Median walk time to the nearest stop, per resident (minutes)\n\n" + md_table(wide(res, "median_min")))
    for th in cfg["share_thresholds_min"]:
        parts.append(
            f"#### Share of residents more than {th} min from the nearest stop\n\n"
            + md_table(wide(res, f"share_over_{th}min", pct=True))
        )

    diff = (bld.set_index(key)["median_min"] - res.set_index(key)["median_min"]).rename("d").reset_index()
    parts.append(
        "#### Effect of resident weighting (building-count median minus resident median, minutes)\n\n"
        "Positive values: counting every building once (sheds, garages, allotment huts included) "
        "makes walks look longer than residents experience them.\n\n"
        + md_table(wide(diff, "d", signed=True))
    )

    berlin = res[res["unit_id"] == "Berlin"].pivot(index="mode", columns="speed_mps", values="median_min").reindex(modes)
    berlin.columns = [f"{c} m/s" for c in berlin.columns]
    berlin = berlin.apply(lambda c: c.map(fmt)).reset_index().rename(columns={"mode": "Mode"})
    parts.append("#### Sensitivity to walking speed (Berlin, median per resident, minutes)\n\n" + md_table(berlin))

    sbuf = cfg.raw.get("stop_buffer_sensitivity_m")
    sens_csv = out / f"walk_time_by_district_stopbuffer_{sbuf}m.csv"
    if sbuf is not None and sens_csv.exists():
        b = pd.read_csv(sens_csv)
        b = b[b["weighting"] == "residents"].set_index(key)["median_min"]
        d = (b - res.set_index(key)["median_min"]).rename("d").reset_index()
        parts.append(
            f"#### Sensitivity to the city limit: stops up to {sbuf} m outside Berlin also counted "
            "(change in median per resident, minutes)\n\n"
            + md_table(wide(d, "d", signed=True))
        )

    older = s[(s["weighting"] == "residents_65plus") & (s["speed_mps"] == 1.0)]
    if len(older):
        rows = []
        for u in order:
            g = older[older["unit_id"] == u].set_index("mode")
            if g.empty:
                continue
            row = {"District": u, "Residents 65+": f"{g['residents'].iloc[0]:,.0f}"}
            for m in ("S- or U-Bahn", "Any mode"):
                if m in g.index:
                    row[f"{m}: median"] = fmt(g.loc[m, "median_min"])
                    row[f"{m}: over 15 min"] = fmt(g.loc[m, "share_over_15min"], pct=True)
            rows.append(row)
        parts.append(
            "#### Older residents (65+) at 1.0 m/s\n\n"
            "Walk per resident aged 65 or over, at a slower pace of 1.0 m/s. Older residents are known per "
            "Planungsraum only, so within a Planungsraum they are spread like all residents; differences from "
            "the all-resident tables at district level come from where older people live and from the slower pace.\n\n"
            + md_table(pd.DataFrame(rows))
        )

    fq = cfg.raw.get("frequency")
    freq_csv = out / f"walk_time_by_district_frequent_{fq['max_headway_min']}min.csv" if fq else None
    if freq_csv is not None and freq_csv.exists():
        f = pd.read_csv(freq_csv)
        f = f[f["weighting"] == "residents"]
        win = f"{fq['window'][0]}-{fq['window'][1]}"
        day = pd.Timestamp(str(fq["date"])).strftime("%A %d %B %Y")
        parts.append(
            f"#### Frequent stops only: median walk per resident (minutes)\n\n"
            f"Only stops with at least one departure every {fq['max_headway_min']} min on average, {win} on "
            f"{day} (counted per stop point and mode).\n\n" + md_table(wide(f, "median_min"))
        )
        parts.append(
            f"#### Frequent stops only: share of residents more than 15 min away\n\n"
            + md_table(wide(f, "share_over_15min", pct=True))
        )
        fs = out / "stops_frequency_by_mode.csv"
        if fs.exists():
            parts.append("#### Frequent stops per mode (inside Berlin)\n\n"
                         + md_table(pd.read_csv(fs).set_index("mode").reindex(cfg["modes"]).reset_index()))

    plr_csv = out / "walk_time_by_planungsraum.csv"
    if plr_csv.exists():
        p = pd.read_csv(plr_csv, dtype={"unit_id": str})
        p = p[(p["weighting"] == "residents") & (p["speed_mps"] == v) & (p["unit_id"] != "Berlin")]
        n_low = int(p.drop_duplicates("unit_id")["low_population"].sum())
        p = p[~p["low_population"]]
        rows = []
        for m in modes:
            x = p.loc[p["mode"] == m, "median_min"]
            q = x.quantile([0.1, 0.5, 0.9])
            rows.append({"Mode": m, "Planungsräume": len(x), "p10": fmt(q[0.1]), "median": fmt(q[0.5]),
                         "p90": fmt(q[0.9]), "max": fmt(x.max())})
        parts.append(
            "#### Spread across LOR Planungsräume (median walk per resident, minutes)\n\n"
            f"Distribution over the {p['unit_id'].nunique()} Planungsräume with at least "
            f"{cfg['min_unit_residents']} residents ({n_low} excluded as low population). Per-unit values are in "
            "`output/walk_time_by_planungsraum.csv` and `output/walk_time_by_bezirksregion.csv`.\n\n"
            + md_table(pd.DataFrame(rows))
        )

    seg_name = "berlin" if (out / "segments_berlin_by_district.csv").exists() else None
    if seg_name:
        bd = pd.read_csv(out / f"segments_{seg_name}_by_district.csv")
        tbl = pd.DataFrame({
            "District": bd["district"],
            "All segments": bd["live_segments"].map(lambda x: f"{x:,}") if "live_segments" in bd else "",
            "Residential segments": bd["segments"].map(lambda x: f"{x:,}"),
            "Residential share": bd["residential_share"].map(lambda x: fmt(x, pct=True)) if "residential_share" in bd else "",
            "Network km": bd["network_km"].map(fmt), "Median segment m": bd["median_segment_m"].map(fmt),
            "Median NAIN 800 m": bd["median_nain_800"].map(lambda x: f"{x:.3f}"),
            "Median NAIN 2000 m": bd["median_nain_2000"].map(lambda x: f"{x:.3f}"),
            "Median NACH 2000 m": bd["median_nach_2000"].map(lambda x: f"{x:.3f}"),
        })
        parts.append("#### Phase 1: segment map and centrality per district\n\n"
                     "One citywide angular segment analysis (city + 2 km buffer, forestry tracks removed); each "
                     "segment assigned to the district containing its midpoint. All streets are used for routing; "
                     "statistics, rankings and maps cover residential streets only (a building with residents "
                     f"within {cfg.raw.get('segment_residential_buffer_m', 50)} m).\n\n" + md_table(tbl))
        t = pd.read_csv(out / f"segments_{seg_name}_top10.csv")
        rows = []
        for dname, g in t.groupby("district"):
            def top3(meas, r):
                x = g[(g["measure"] == meas) & (g["radius_m"] == r)].sort_values("rank").head(3)
                return ", ".join(x["street"].str.title())
            rows.append({"District": dname, "Angular choice 2000 m": top3("angular choice", 2000),
                         "NAIN 2000 m": top3("NAIN", 2000), "NAIN 800 m": top3("NAIN", 800)})
        parts.append("#### Phase 1: top three named streets per district\n\n"
                     "A street's value is its highest segment; full top-10 lists in "
                     f"`output/segments_{seg_name}_top10.csv`.\n\n" + md_table(pd.DataFrame(rows)))
        ms = out / f"segments_{seg_name}_main_streets.csv"
        if ms.exists():
            m = pd.read_csv(ms)
            tbl = pd.DataFrame({
                "District": m["district"], "Street": m["street"].str.title(), "Segments": m["segments"],
                "Choice 800 m": m["choice_800_pct"].map(lambda x: fmt(100 * x)),
                "Choice 2000 m": m["choice_2000_pct"].map(lambda x: fmt(100 * x)),
                "NACH 2000 m": m["nach_2000_pct"].map(lambda x: fmt(100 * x)),
                "NAIN 2000 m": m["nain_2000_pct"].map(lambda x: fmt(100 * x)),
            })
            parts.append("#### Phase 1 sanity check: where known main streets rank\n\n"
                         "Median percentile of each street's segments among the residential segments of its "
                         "district (100 = most central).\n\n" + md_table(tbl))
        for cmp_csv in sorted(out.glob("segments_*_vs_berlin.csv")):
            c = pd.read_csv(cmp_csv)
            c = c[c["radius_m"].isin([800, 2000])]
            tbl = pd.DataFrame({"Radius m": c["radius_m"], "Measure": c["measure"],
                                "Matched segments": c["matched_segments"], "Spearman": c["spearman"].map(lambda x: f"{x:.3f}"),
                                "Median relative difference": c["median_abs_rel_diff"].map(lambda x: fmt(x, pct=True))})
            dname = cmp_csv.name[len("segments_"):-len("_vs_berlin.csv")]
            parts.append(f"#### Phase 1 check: pilot run ({dname} + 2 km) against the citywide run\n\n"
                         f"Same segments matched by midpoint and length "
                         f"({fmt(c['share_matched'].iloc[0], pct=True)} of the pilot's segments matched). Values near "
                         "1 and 0% mean the 2 km buffer removes edge effects.\n\n" + md_table(tbl))

    stops_csv = out / "stops_by_mode.csv"
    if stops_csv.exists():
        st = pd.read_csv(stops_csv).set_index("mode").reindex(cfg["modes"]).reset_index()
        parts.append("#### GTFS stops per mode\n\n" + md_table(st))

    prov = []
    if meta.get("gtfs_feed"):
        prov.append("GTFS feed: " + ", ".join(f"{k}={val}" for k, val in meta["gtfs_feed"].items()))
    for k, d in meta.get("downloads", {}).items():
        prov.append(f"{k}: downloaded {d.get('downloaded_utc')} from {d.get('url')}")
    if meta.get("buildings"):
        b = meta["buildings"]
        prov.append(f"Buildings: {b.get('buildings_used')} (excluded for snap distance > "
                    f"{cfg['max_building_snap_m']} m: {b.get('buildings_snap_over_max')})")
    if meta.get("residents"):
        r = meta["residents"]
        prov.append(f"Residents: {r.get('register_total')} in the register, {r.get('allocated_total')} allocated to "
                    f"{r.get('candidate_buildings')} residential candidate buildings; storeys mapped for "
                    f"{fmt(r.get('levels_known_share_of_candidates'), pct=True)} of them")
    if meta.get("generated_utc"):
        prov.append(f"Pipeline run: {meta['generated_utc']}")
    if prov:
        parts.append("#### Provenance\n\n" + "\n".join(f"- {x}" for x in prov))

    return "\n\n".join(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    cfg = load_config(ap.parse_args().config)
    readme = cfg.root / "README.md"
    text = readme.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise SystemExit(f"README.md is missing the markers:\n{BEGIN}\n{END}")
    new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: f"{BEGIN}\n\n{build(cfg)}\n\n{END}", text, flags=re.S)
    readme.write_text(new, encoding="utf-8")
    print("README.md results section regenerated")
