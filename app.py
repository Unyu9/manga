#!/usr/bin/env python3
"""
Grimmory AniList Sidecar Tool - interactive web UI

Browse your manga folders, search AniList, confirm the right series,
review/adjust per-volume numbers, and generate Grimmory-compatible
.metadata.json sidecar files - all from a browser instead of a CLI.

Flow:
  /            -> pick a series folder (subfolder of BOOKS_ROOT)
  /search      -> search AniList for that folder's title
  /select      -> confirm which AniList result is the right one
  /review      -> review parsed volume numbers per file, edit if wrong
  /generate    -> write the sidecar files, show a summary

Env vars:
  BOOKS_ROOT          Root folder containing your series subfolders (default /books)
  FLASK_SECRET_KEY    Any random string (used only to sign the session cookie)

IMPORTANT: confirmed against a real Grimmory-exported sidecar - series
info is a nested object: {"name": ..., "number": ...}. The "total"
field name for series total count is still a guess (not present in
the sample sidecar since it was a single book, not part of a known-
length series) - double check if Grimmory ignores/rejects it.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error

from flask import Flask, render_template, request as flask_request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

BOOKS_ROOT = Path(os.environ.get("BOOKS_ROOT", "/books"))
ANILIST_URL = "https://graphql.anilist.co"
BOOK_EXTENSIONS = {".cbz", ".cbr", ".cb7", ".epub", ".pdf"}
VOLUME_NUM_RE = re.compile(r"(?:vol(?:ume)?\.?\s*)(\d{1,4})", re.IGNORECASE)

SEARCH_QUERY = """
query ($search: String) {
  Page(page: 1, perPage: 8) {
    media(search: $search, type: MANGA, sort: SEARCH_MATCH) {
      id
      title { romaji english native }
      coverImage { medium }
      format
      status
      startDate { year }
      volumes
    }
  }
}
"""

DETAIL_QUERY = """
query ($id: Int) {
  Media(id: $id) {
    id
    title { romaji english native }
    description(asHtml: false)
    genres
    volumes
    status
    startDate { year month day }
    staff(perPage: 5) {
      edges { role node { name { full } } }
    }
  }
}
"""


def anilist_query(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = request.Request(
        ANILIST_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def clean_description(html_desc: str) -> str:
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
        return f"{sd['year']:04d}-{sd.get('month') or 1:02d}-{sd.get('day') or 1:02d}"
    return None


def list_series_folders() -> list[str]:
    if not BOOKS_ROOT.is_dir():
        return []
    return sorted(p.name for p in BOOKS_ROOT.iterdir() if p.is_dir())


def resolve_folder(folder_name: str) -> Path | None:
    """Only allow folders that actually exist directly under BOOKS_ROOT."""
    if folder_name in list_series_folders():
        return BOOKS_ROOT / folder_name
    return None


def list_book_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in BOOK_EXTENSIONS)


def extract_volume_number(filename: str) -> int | None:
    match = VOLUME_NUM_RE.search(filename)
    return int(match.group(1)) if match else None


@app.route("/")
def index():
    folders = list_series_folders()
    return render_template("index.html", folders=folders, books_root=str(BOOKS_ROOT))


@app.route("/search", methods=["POST"])
def search():
    folder_name = flask_request.form["folder"]
    title = flask_request.form.get("title", "").strip() or folder_name

    if resolve_folder(folder_name) is None:
        flash(f"Folder not found: {folder_name}")
        return redirect(url_for("index"))

    try:
        data = anilist_query(SEARCH_QUERY, {"search": title})
    except error.HTTPError as e:
        flash(f"AniList search failed: {e.code}")
        return redirect(url_for("index"))

    results = data.get("data", {}).get("Page", {}).get("media", [])
    return render_template("search.html", folder=folder_name, title=title, results=results)


@app.route("/select", methods=["POST"])
def select():
    folder_name = flask_request.form["folder"]
    anilist_id = int(flask_request.form["anilist_id"])

    folder = resolve_folder(folder_name)
    if folder is None:
        flash(f"Folder not found: {folder_name}")
        return redirect(url_for("index"))

    try:
        data = anilist_query(DETAIL_QUERY, {"id": anilist_id})
    except error.HTTPError as e:
        flash(f"AniList lookup failed: {e.code}")
        return redirect(url_for("index"))

    media = data.get("data", {}).get("Media")
    if not media:
        flash("AniList entry not found.")
        return redirect(url_for("index"))

    matched_title = media["title"].get("english") or media["title"].get("romaji")
    description = clean_description(media.get("description", ""))
    genres = media.get("genres", [])
    authors = build_authors(media)
    series_total = media.get("volumes")
    published_date = build_published_date(media)

    files = list_book_files(folder)
    rows = []
    for f in files:
        rows.append({"filename": f.name, "volume": extract_volume_number(f.stem) or ""})

    return render_template(
        "review.html",
        folder=folder_name,
        matched_title=matched_title,
        description=description,
        genres=genres,
        authors=authors,
        series_total=series_total if series_total is not None else "",
        published_date=published_date or "",
        rows=rows,
    )


@app.route("/generate", methods=["POST"])
def generate():
    folder_name = flask_request.form["folder"]
    folder = resolve_folder(folder_name)
    if folder is None:
        flash(f"Folder not found: {folder_name}")
        return redirect(url_for("index"))

    matched_title = flask_request.form["matched_title"]
    description = flask_request.form.get("description", "")
    genres = [g for g in flask_request.form.get("genres", "").split(",") if g]
    authors = [a for a in flask_request.form.get("authors", "").split(",") if a]
    series_total_raw = flask_request.form.get("series_total", "").strip()
    series_total = int(series_total_raw) if series_total_raw.isdigit() else None
    published_date = flask_request.form.get("published_date", "").strip() or None

    filenames = flask_request.form.getlist("filename")
    volumes = flask_request.form.getlist("volume")

    written, skipped = [], []
    for filename, vol_raw in zip(filenames, volumes):
        vol_raw = vol_raw.strip()
        if not vol_raw.isdigit():
            skipped.append(filename)
            continue
        vol_num = int(vol_raw)

        series_obj = {"name": matched_title, "number": vol_num}
        if series_total is not None:
            series_obj["total"] = series_total  # field name not yet confirmed - see README

        sidecar = {
            "version": "1.0",
            "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generatedBy": "grimmory-sidecar-tool",
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

        book_path = folder / filename
        out_path = book_path.with_suffix("").with_suffix(".metadata.json")
        out_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(out_path.name)

    return render_template("result.html", folder=folder_name, written=written, skipped=skipped)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
