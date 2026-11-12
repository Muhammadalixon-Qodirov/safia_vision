"""Download the clips listed in config/videos.json into videos/ (kept out of git) and
write videos/ATTRIBUTION.md.

Each entry is either a direct file (`download_url`, e.g. a Pexels/Pixabay mp4) or a
YouTube video (`youtube_id` + `height`, fetched with yt-dlp: pip install yt-dlp).
The lines and zones in config/*.yaml are pixel coordinates, so after downloading the
script checks each clip's resolution against `expect`.

    python scripts/download_videos.py            # all clips
    python scripts/download_videos.py shop1.mp4  # only some

Do NOT use any Safia footage.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

MANIFEST = Path("config/videos.json")
# Pexels/Pixabay CDNs reject the default "Python-urllib" user agent with 403.
USER_AGENT = "Mozilla/5.0 (compatible; store-analytics/1.0; public-clip-downloader)"


def _download_file(url: str, dst: Path):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dst, "wb") as out:
        shutil.copyfileobj(resp, out)


def _download_youtube(video_id: str, height: int, dst: Path):
    # video only (no audio needed), mp4, the exact height the configs were drawn on
    fmt = f"bv*[ext=mp4][height={height}]/bv*[height={height}]"
    cmd = [sys.executable, "-m", "yt_dlp", "-f", fmt, "-o", str(dst), "--no-playlist",
           "--", f"https://www.youtube.com/watch?v={video_id}"]
    subprocess.run(cmd, check=True)


def _check(dst: Path, expect: str):
    try:
        import cv2
    except ImportError:
        return
    c = cv2.VideoCapture(str(dst))
    got = f"{int(c.get(3))}x{int(c.get(4))}"
    want = expect.split(",")[0].strip()
    print(f"  {dst.name}: {got}" + ("  ok" if got == want else f"  <-- expected {want}: lines/zones will be off"))


def main():
    only = set(sys.argv[1:])
    items = [it for it in json.loads(MANIFEST.read_text(encoding="utf-8"))
             if not only or it["filename"] in only]
    Path("videos").mkdir(exist_ok=True)
    attribution = ["# Video attribution", "", "Public clips only. No Safia footage is used.", ""]
    for it in items:
        dst = Path("videos") / it["filename"]
        if not dst.exists():
            print(f"downloading {it['filename']} ...")
            if it.get("youtube_id"):
                _download_youtube(it["youtube_id"], int(it["height"]), dst)
            else:
                _download_file(it["download_url"], dst)
        if it.get("expect"):
            _check(dst, it["expect"])
        attribution.append(
            f"- **{it['filename']}** - \"{it.get('title', '')}\" by {it['author']}; {it['licence']} "
            f"(<{it['licence_url']}>); source: <{it['source_url']}>; used {it.get('timestamps', '')}")
    (Path("videos") / "ATTRIBUTION.md").write_text("\n".join(attribution) + "\n", encoding="utf-8")
    print("attribution -> videos/ATTRIBUTION.md")


if __name__ == "__main__":
    main()
