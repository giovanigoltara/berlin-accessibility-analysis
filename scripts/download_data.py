"""Download the inputs listed under `downloads` in config.yaml into data/raw/.

Writes data/raw/download_log.json (URL, time, size, sha256) so the run
metadata can record which data versions produced the results.
"""
import argparse
import hashlib
import json
import time
import urllib.request

import _bootstrap  # noqa: F401

from berlin_access.config import load_config


def fetch(url, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "berlin-accessibility-analysis/0.1 (research)"})
    with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
        final_url = r.geturl()
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return {
        "url": url,
        "final_url": final_url,
        "downloaded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bytes": dest.stat().st_size,
        "sha256": h.hexdigest(),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--force", action="store_true", help="re-download existing files")
    args = ap.parse_args()
    cfg = load_config(args.config)
    log_path = cfg.path("pbf").parent / "download_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    failed = []
    for key, url in cfg["downloads"].items():
        dest = cfg.path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not args.force:
            print(f"exists, skipping: {dest}")
            continue
        print(f"downloading {url} -> {dest}")
        try:
            log[key] = fetch(url, dest)
        except OSError as e:
            failed.append(key)
            print(f"FAILED {key}: {e}")
    log_path.write_text(json.dumps(log, indent=2))
    if failed:
        raise SystemExit(f"download failed for: {', '.join(failed)}")
