# Grimmory Sidecar Tool

A small local web UI that generates Grimmory-compatible `.metadata.json`
sidecar files for manga, sourced from AniList (which Grimmory doesn't
support natively).

## Run it (Synology / Container Manager / Portainer)

1. Copy this whole folder onto your NAS, e.g. `/volume1/docker/grimmory-sidecar-tool/`
2. Edit `docker-compose.yml`:
   - Set the volume mount to wherever your manga library folders actually live
     (should match the path Grimmory itself scans)
   - Optionally change `FLASK_SECRET_KEY` to a random string
3. In Container Manager (or Portainer), create a new project pointing at
   this folder, or run from the CLI:

   ```bash
   cd /volume1/docker/grimmory-sidecar-tool
   docker compose up -d --build
   ```

4. Open `http://<nas-ip>:5005` in a browser

## Using it

1. Pick a series folder (subfolders of your books root show up automatically)
2. Pick the correct match from AniList's search results
3. Review the series description/genres/authors, and check the volume
   number parsed from each filename (edit any that got it wrong)
4. Click "Generate sidecar files" - writes one `.metadata.json` per book
5. In Grimmory: Settings > Metadata 2 > your manga library > Import Sidecar

## Auto-import into Grimmory (optional)

By default you still need to click Import Sidecar in Grimmory after running
this tool. To have it import automatically instead, set these in
`docker-compose.yml`:

- `GRIMMORY_BASE_URL` - e.g. `http://192.168.0.33:6060`
- `GRIMMORY_USERNAME` / `GRIMMORY_PASSWORD` - a Grimmory login. Consider
  creating a separate user for this (Settings > Users) rather than using
  your admin account, since the password is stored in plain text in the
  compose file.
- `GRIMMORY_LIBRARY_NAME` - must match your manga library's name exactly
  (default: `Manga`)

With these set, after generating sidecars the tool logs into Grimmory's API
and calls its bulk sidecar import endpoint automatically - no manual click
needed.

## Notes

- JoJo's Bizarre Adventure is split into separate AniList entries per part -
  search using a part-specific title (e.g. "JoJo's Bizarre Adventure Part 1")
  if the plain series name doesn't surface the right one, and run each
  part's folder through separately.
- The `seriesName` / `seriesNumber` / `seriesTotal` field names in `app.py`
  are my best inference from Grimmory's docs - verify them against a real
  sidecar exported from your Grimmory library (Metadata Center > Sidecar
  tab > Export on any existing book) and adjust in `app.py` if they differ.
- AniList only has series-level descriptions/covers, not per-volume - every
  volume in a series gets the same description. Per-volume covers aren't
  fetched by this tool.
- No data is sent anywhere except to AniList's public GraphQL API
  (`graphql.anilist.co`).
