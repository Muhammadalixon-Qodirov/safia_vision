"""Download the public test clips listed in config/videos.json into videos/
(kept out of git) and write videos/ATTRIBUTION.md.

Only public footage whose licence allows download, processing and display may be
used (Pexels, Pixabay, or a public dataset whose licence permits it). Do NOT use
any Safia footage. You fill config/videos.json with the clips you picked and
their licence details; this script just fetches them and records attribution.

    python scripts/download_videos.py
"""
from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

MANIFEST = Path("config/videos.json")

# Pexels/Pixabay CDNs reject the default "Python-urllib" user agent with 403, so
# send a normal one. These files are free to download under their licence.
USER_AGENT = "Mozilla/5.0 (compatible; store-analytics/1.0; public-clip-downloader)"

TEMPLATE = [
    {
        "filename": "entrance.mp4",
        "download_url": "<direct .mp4 URL of a public clip of people at an entrance>",
        "source_url": "<the Pexels/Pixabay page URL>",
        "author": "<author name>",
        "licence": "Pexels License",
        "licence_url": "https://www.pexels.com/license/",
        "timestamps": "0:00-2:30",
    },
    {
        "filename": "counter.mp4",
        "download_url": "<direct .mp4 URL of a public clip of a counter/till with a queue>",
        "source_url": "<the Pexels/Pixabay page URL>",
        "author": "<author name>",
        "licence": "Pexels License",
        "licence_url": "https://www.pexels.com/license/",
        "timestamps": "0:00-3:00",
    },
]


def main():
    if not MANIFEST.exists():
        MANIFEST.parent.mkdir(exist_ok=True)
        MANIFEST.write_text(json.dumps(TEMPLATE, indent=2), encoding="utf-8")
        print(f"wrote template {MANIFEST}. Fill in real public clips + licences, then re-run.")
        return
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    Path("videos").mkdir(exist_ok=True)
    attribution = ["# Video attribution", "",
                   "Public footage only. No Safia footage is used.", ""]
    for it in items:
        dst = Path("videos") / it["filename"]
        url = it["download_url"]
        if url.startswith("<"):
            print(f"skip {it['filename']}: fill in download_url in {MANIFEST}")
            continue
        if not dst.exists():
            print(f"downloading {it['filename']} ...")
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as resp, open(dst, "wb") as out:
                shutil.copyfileobj(resp, out)
            print(f"  -> {dst} ({dst.stat().st_size // (1024 * 1024)} MB)")
        attribution.append(
            f"- **{it['filename']}** - {it['author']}, {it['licence']} "
            f"(<{it['licence_url']}>); source: <{it['source_url']}>; used {it.get('timestamps', '')}")
    (Path("videos") / "ATTRIBUTION.md").write_text("\n".join(attribution) + "\n", encoding="utf-8")
    print("attribution -> videos/ATTRIBUTION.md (copy it into the README)")


if __name__ == "__main__":
    main()
