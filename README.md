# Music Artwork Finder

A Streamlit app for music industry professionals to bulk-search and download high-resolution album, single, and artist artwork from Spotify and iTunes.

## Prerequisites

- Python 3.10+
- pip (or pip3)
- A Spotify Developer account (optional — iTunes search works without any credentials)

## Quick Start

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Run the app:**
```bash
streamlit run app.py
```
This will open the app in your browser automatically at `http://localhost:8501`.

3. **Use it:**
   - Paste songs or upload a CSV in the main panel
   - Click "Search for Artwork"
   - Select your preferred artwork from each result row
   - Download images individually or as a ZIP

## Spotify Setup (Optional but Recommended)

Spotify returns higher-quality and more accurate results. iTunes search works out of the box without any credentials, but with one important limitation: **iTunes does not support artist photo searches.** If you search by artist name only without Spotify enabled, iTunes will return album artwork instead of an artist photo.

To enable Spotify (and unlock true artist photo search):
1. Go to https://developer.spotify.com/dashboard
2. Create an app
3. Copy your Client ID and Client Secret into the sidebar

## Test Data

Use `sample_music_entries.csv` to test — just upload it in the app.

## Input Format

**Text input** (one entry per line):
```
Artist                        → Artist photo search
Artist - Song                 → Single/track artwork
Artist - Album                → Album artwork
```

**CSV:**
Must have an `Artist` column. `Track` and `Album` are optional.

## How Search Works

The app queries Spotify and iTunes for each entry. Spotify results are preferred when available; iTunes is used as a fallback. Artwork is returned at up to 3000×3000px resolution.

## Error Handling

API failures (bad credentials, rate limits, network timeouts) surface as inline warnings in the UI rather than silently returning empty results. Each failed query shows the HTTP status code and the entry it was searching for.

## Troubleshooting

- **"Module not found"** → Run `pip install -r requirements.txt` again
- **Spotify warnings in UI** → Check your credentials in the sidebar; iTunes will still work
- **Port in use** → Close other terminals or run with `streamlit run app.py --server.port 8502`
- **iTunes returns wrong artwork** → Add an `Album` column to your CSV to narrow results
- **App doesn't open in browser** → Navigate manually to `http://localhost:8501`

## Legal Notice

This tool is for **internal editorial and operational use only**. Album artwork is copyrighted material owned by labels and artists. Usage that falls outside your organization's licensing agreements — including commercial redistribution or creating derivative works — is not permitted. Consult your legal or compliance team if you have questions about usage rights.

## Built With

- [Streamlit](https://streamlit.io/) — web interface
- [Spotify Web API](https://developer.spotify.com/documentation/web-api) — primary artwork source
- [iTunes Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI) — fallback artwork source
