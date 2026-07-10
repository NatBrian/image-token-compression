"""Backfill per-arm image counts for the claude runs, WITHOUT touching results.json.

The claude drivers fold only Anthropic's `/v1/messages` usage into results.json, and
that usage object carries no image count, so every claude item shows `imgs = n/a` in
the report even when the proxy imaged plenty. The truth lives in the proxy event log
(`proxy_{arm}[_tag]_events.jsonl`) that sits next to each run's results: every real
model call is one line carrying `transform.image_count`.

This script reads those event logs (read-only) and writes ONE derived, tracked sidecar
`bench/image_backfill.json`, keyed by the event file's path relative to bench/:

    { "campaign_.../claude_longdoc/proxy_on_events.jsonl": {"calls": 10, "images": 30},
      ... }

`calls`  = model calls that went through imaging (path /v1/messages, status 200, with a
           `transform` block, which excludes 403/404 warmup pokes and count_tokens probes).
`images` = sum of transform.image_count over those calls.

The report loads this sidecar to populate claude image counts and the avg-images-per-call
column. results.json is never modified; the sidecar is the only new artifact, and it is
tracked so the report stays reproducible even though the raw event logs are gitignored.

Note on attribution: the proxy log path is per-ARM (on/off[/tools0]), not per-config, and
imgctx opens it in append mode. A folder that runs >1 config into one arm (claude longdoc:
narrativeqa + gov_report) therefore has a single combined event file, so those counts are
folder-level, not per-config, and the report marks them.

Run:  .venv/bin/python -m bench.backfill_images
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

from bench._report_data import RUN_DIRS  # single source of truth for folders

OUT = Path("bench/image_backfill.json")


def scan_events(path: str) -> dict:
    """Sum imaging calls + images from one proxy event log."""
    calls = images = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            # Only real model calls that reached imaging carry a transform block.
            tr = e.get("transform")
            if not isinstance(tr, dict):
                continue
            if e.get("path") != "/v1/messages" or e.get("status") != 200:
                continue
            calls += 1
            images += int(tr.get("image_count") or 0)
    return {"calls": calls, "images": images}


def main() -> None:
    side: dict[str, dict] = {}
    for d in RUN_DIRS:
        for f in sorted(glob.glob(f"bench/{d}/**/proxy_*events*.jsonl", recursive=True)):
            rel = f[len("bench/"):]
            side[rel] = scan_events(f)
    OUT.write_text(json.dumps(side, indent=2, sort_keys=True))
    n_img = sum(v["images"] for v in side.values())
    print(f"wrote {OUT}  ({len(side)} event logs, {n_img} images total)")


if __name__ == "__main__":
    main()
