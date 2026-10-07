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

BEGIN = "<!-- BEGIN GENERATED: results (scripts/build_readme_tables.py) -->"
END = "<!-- END GENERATED: results -->"


def fmt(x, pct=False):
    if pd.isna(x):
        return "n/a"
    return f"{100 * x:.1f}%" if pct else f"{x:.1f}"


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def build(cfg) -> str:
    out = cfg.path("output")
    summary_csv = out / "walk_time_by_district.csv"
    if not summary_csv.exists():
        return (
            "_Results have not been generated yet. Run `python scripts/run_accessibility.py` and then "
            "`python scripts/build_readme_tables.py`. The table in earlier versions of this README did not "
            "come from the code and has been removed; the buggy v0 output is kept in `output/legacy/` "
            "for reference only._"
        )
    s = pd.read_csv(summary_csv)
    modes = cfg["modes"]
    v_main = cfg["walk_speed_main_mps"]
    meta = json.loads((out / "run_metadata.json").read_text()) if (out / "run_metadata.json").exists() else {}
    parts = []

    main = s[s["speed_mps"] == v_main]
    order = ["Berlin"] + sorted(d for d in main["district"].unique() if d != "Berlin")

    def wide(col, pct=False):
        w = main.pivot(index="district", columns="mode", values=col).reindex(index=order, columns=modes)
        w = w.apply(lambda c: c.map(lambda x: fmt(x, pct)))
        return w.reset_index().rename(columns={"district": "District"})

    parts.append(f"#### Median walk time to the nearest stop (minutes, {v_main} m/s)\n\n" + md_table(wide("median_min")))
    for th in cfg["share_thresholds_min"]:
        col = f"share_over_{th}min"
        parts.append(f"#### Share of buildings more than {th} min from the nearest stop ({v_main} m/s)\n\n" + md_table(wide(col, pct=True)))

    sens = s[s["district"] == "Berlin"].pivot(index="mode", columns="speed_mps", values="median_min").reindex(modes)
    sens.columns = [f"{c} m/s" for c in sens.columns]
    sens = sens.apply(lambda c: c.map(fmt)).reset_index().rename(columns={"mode": "Mode"})
    parts.append("#### Sensitivity to walking speed (Berlin-wide median, minutes)\n\n" + md_table(sens))

    buf = cfg.raw.get("stop_buffer_sensitivity_m")
    sens_csv = out / f"walk_time_by_district_stopbuffer_{buf}m.csv"
    if buf is not None and sens_csv.exists():
        b = pd.read_csv(sens_csv)
        b = b[b["speed_mps"] == v_main].set_index(["district", "mode"])["median_min"]
        a = main.set_index(["district", "mode"])["median_min"]
        diff = (b - a).unstack("mode").reindex(index=order, columns=modes)
        diff = diff.apply(lambda c: c.map(lambda x: "n/a" if pd.isna(x) else f"{x:+.1f}"))
        parts.append(
            f"#### Sensitivity to the city limit: stops up to {buf} m outside Berlin instead of "
            f"{cfg['stop_buffer_m']} m (change in median, minutes, {v_main} m/s)\n\n"
            f"Main results above count stops up to {cfg['stop_buffer_m']} m outside Berlin. "
            f"Values show how the median changes when the limit is {buf} m instead "
            "(0 m = only stops inside Berlin).\n\n"
            + md_table(diff.reset_index().rename(columns={"district": "District"}))
        )

    stops_csv = out / "stops_by_mode.csv"
    if stops_csv.exists():
        st = pd.read_csv(stops_csv).set_index("mode").reindex(modes).reset_index()
        parts.append("#### GTFS stops used per mode\n\n" + md_table(st))

    prov = []
    if meta.get("gtfs_feed"):
        prov.append("GTFS feed: " + ", ".join(f"{k}={v}" for k, v in meta["gtfs_feed"].items()))
    for k, d in meta.get("downloads", {}).items():
        prov.append(f"{k}: downloaded {d.get('downloaded_utc')} from {d.get('url')}")
    if meta.get("buildings"):
        b = meta["buildings"]
        prov.append(f"Buildings used: {b.get('buildings_used')} (excluded for snap distance > "
                    f"{cfg['max_building_snap_m']} m: {b.get('buildings_snap_over_max')})")
    if meta.get("generated_utc"):
        prov.append(f"Pipeline run: {meta['generated_utc']}")
    if prov:
        parts.append("#### Provenance\n\n" + "\n".join(f"- {p}" for p in prov))

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
