#!/usr/bin/env python3
"""
grimmory_anilist_sidecar.py

Generates Grimmory-compatible .metadata.json sidecar files for manga
volumes, sourced from AniList instead of Grimmory's built-in providers
(none of which know about AniList/manga specifically).

How it works:
  1. You give it a folder containing volume files for one series
     (e.g. /books/One Piece/One Piece Vol 01.cbz, Vol 02.cbz, ...)
  2. It searches AniList by series title (no hardcoded IDs - titles
     can be ambiguous, so it prints the match it picked and lets you
     bail out if it's wrong)
  3. It parses the volume number out of each filename
  4. It writes "<filename-without-ext>.metadata.json" next to each
     book, following Grimmory's sidecar schema

IMPORTANT - before relying on this:
  AniList's manga entries are series-level. It does NOT have
  per-volume descriptions, ISBNs, or page counts. This script gives
  you accurate series-level data (title, synopsis, genres, authors,
  volume count, status) applied across all volumes, with the volume
  number/series position parsed from your filenames. It won't get you
  per-volume covers or ISBNs - for that you'd need to also hit
  MangaDex per volume, which isn't included here yet.

  Also: confirm the exact JSON key names Grimmory expects for
  series fields by exporting a sidecar from an existing book in
  your library first (Metadata Center -> Sidecar tab -> Export).
  The keys used below (seriesName, seriesNumber, seriesTotal) are
  my best inference from Grimmory's docs, not confirmed - check
  one real exported sidecar and adjust the SIDECAR key names near
  the bottom of this script if they differ.

Usage:
    python3 grimmory_anilist_sidecar.py "/books/One Piece" --title "One Piece"
    python3 grimmory_anilist_sidecar.py "/books/JoJo's Bizarre Adventure" --title "JoJo's Bizarre Adventure"
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error

ANILIST_URL = "https://graphql.anilist.co"

ANILIST_QUERY = """
query ($search: String) {
  Media(search: $search, type: MANGA) {
    id
    title { romaji english native }
    description(asHtml: false)
    genres
    volumes
    status
    startDate { year month day }
    staff(perPage: 5) {
      edges {
        role
        node { name { full } }
      }
    }
  }
}
"""

VOLUME_NUM_RE = re.compile(r"(?:vol(?:ume)?\.?\s*)(\d{1,4})", re.IGNORECASE)
BOOK_EXTENSIONS = {".cbz", ".cbr", ".cb7", ".epub", ".pdf"}


def anilist_search(title: str) -> dict:
    payload = json.dumps({"query": ANILIST_QUERY, "variables": {"search": title}}).encode()
    req = request.Request(
        ANILIST_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except error.HTTPError as e:
        print(f"AniList request failed: {e.code} {e.read().decode(errors='ignore')}", file=sys.stderr)
        sys.exit(1)

    media = data.get("data", {}).get("Media")
    if not media:
        print(f"No AniList match found for '{title}'. Try a more exact title.", file=sys.stderr)
        sys.exit(1)
    return media


def extract_volume_number(filename: str) -> int | None:
    match = VOLUME_NUM_RE.search(filename)
    if match:
        return int(match.group(1))
    return None


def clean_description(html_desc: str) -> str:
    # AniList descriptions often contain <br> and <i> tags - strip basic HTML
    text = re.sub(r"<br\s*/?>", "\n", html_desc or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def build_authors(media: dict) -> list[str]:
    names = []
    for edge in media.get("staff", {}).get("edges", []):
        role = (edge.get("role") or "").lower()
        if "story" in role or "art" in role or "creator" in role:
            name = edge["node"]["name"]["full"]
            if name not in names:
                names.append(name)
    return names


def build_published_date(media: dict) -> str | None:
    sd = media.get("startDate") or {}
    if sd.get("year"):
        y = sd["year"]
        m = sd.get("month") or 1
        d = sd.get("day") or 1
        return f"{y:04d}-{m:02d}-{d:02d}"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="Folder containing the volume files for one series")
    parser.add_argument("--title", required=True, help="Series title to search on AniList")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written, don't write files")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Not a folder: {folder}", file=sys.stderr)
        sys.exit(1)

    media = anilist_search(args.title)
    matched_title = media["title"].get("english") or media["title"].get("romaji")
    print(f"AniList match: '{matched_title}' (id={media['id']}) - "
          f"{media.get('volumes') or '?'} volumes, status={media.get('status')}")
    confirm = input("Use this match? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted. Try a more specific --title.")
        sys.exit(0)

    description = clean_description(media.get("description", ""))
    genres = media.get("genres", [])
    authors = build_authors(media)
    series_total = media.get("volumes")
    published_date = build_published_date(media)

    book_files = sorted(p for p in folder.iterdir() if p.suffix.lower() in BOOK_EXTENSIONS)
    if not book_files:
        print(f"No book files found in {folder} (looked for {BOOK_EXTENSIONS})", file=sys.stderr)
        sys.exit(1)

    written = 0
    for book_file in book_files:
        vol_num = extract_volume_number(book_file.stem)
        if vol_num is None:
            print(f"  Skipping (couldn't parse volume number): {book_file.name}")
            continue

        series_obj = {"name": matched_title, "number": vol_num}
        if series_total is not None:
            series_obj["total"] = series_total  # field name not yet confirmed

        sidecar = {
            "version": "1.0",
            "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generatedBy": "grimmory_anilist_sidecar.py",
            "metadata": {
                "title": f"{matched_title}, Vol. {vol_num}",
                "authors": authors,
                "description": description,
                "categories": genres,
                "language": "English",
                "series": series_obj,
            },
        }
        if published_date:
            sidecar["metadata"]["publishedDate"] = published_date

        out_path = book_file.with_suffix("").with_suffix(".metadata.json")
        if args.dry_run:
            print(f"  [dry-run] would write {out_path.name}")
        else:
            out_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  wrote {out_path.name}")
        written += 1

    print(f"\nDone. {written} sidecar file(s) {'would be ' if args.dry_run else ''}written.")
    print("Next: Grimmory -> Settings > Metadata 2 -> your manga library -> Import Sidecar.")


if __name__ == "__main__":
    main()
