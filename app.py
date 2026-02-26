"""
Music Artwork Finder
====================
A Streamlit app for searching and downloading music artwork via Spotify and iTunes APIs.

Architecture:
  - Constants / config at the top
  - API layer: token fetching, Spotify search, iTunes search, image download
  - Parsing layer: text input and CSV input parsing
  - UI layer: sidebar, input tabs, results gallery, download controls

Author: Rosalie Cabison | Music & Tech PM
"""

import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import zipfile
import os
from typing import Optional

# ============================================
# CONSTANTS
# ============================================

ITUNES_ARTWORK_SIZE = "3000x3000bb"
ITUNES_ARTWORK_PREVIEW_SIZE = "100x100bb"
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"

# Map search type to Spotify API `type` parameter values
SPOTIFY_TYPE_MAP = {
    "artist": "artist",
    "track": "track",
    "album": "album",
    "track_or_album": "track,album",
}

# ============================================
# TYPE ALIASES
# ============================================
# A search result is a dict with keys: source, image_url, album_name, type, found, etc.
ArtworkResult = dict
SearchType = str  # "artist" | "track" | "album" | "track_or_album"


# ============================================
# API LAYER
# ============================================

@st.cache_data
def fetch_spotify_token(client_id: str, client_secret: str) -> Optional[str]:
    """
    Exchange Spotify client credentials for a bearer token.
    Returns None and surfaces a user-visible warning on failure.
    Cached so the token is reused across reruns within the same session.
    """
    try:
        response = requests.post(
            SPOTIFY_AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]
    except requests.HTTPError as e:
        st.warning(f"Spotify auth failed (HTTP {e.response.status_code}). Check your credentials.")
        return None
    except Exception as e:
        st.warning(f"Spotify auth failed: {e}")
        return None


@st.cache_data
def search_spotify(
    artist: str,
    track: str,
    client_id: str,
    client_secret: str,
    search_type: SearchType = "track_or_album",
    album: str = "",
) -> list[ArtworkResult]:
    """
    Search Spotify for artwork matching the given artist/track/album.

    Returns a list of result dicts, each containing:
      - source, image_url, width, height, album_name, type, found

    Returns an empty list on any failure so callers don't need try/except.
    """
    token = fetch_spotify_token(client_id, client_secret)
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}"}

    try:
        if search_type == "artist":
            return _spotify_artist_search(artist, headers)
        elif search_type == "album":
            return _spotify_album_search(artist, album, headers)
        else:
            # "track", "track_or_album" — search by track name
            return _spotify_track_search(artist, track, headers)

    except requests.HTTPError as e:
        st.warning(f"Spotify search failed (HTTP {e.response.status_code}) for '{artist} - {track}'.")
        return []
    except Exception as e:
        st.warning(f"Spotify search error for '{artist} - {track}': {e}")
        return []


def _spotify_artist_search(artist: str, headers: dict) -> list[ArtworkResult]:
    """Return artist photo results from Spotify. Only exact name matches are kept."""
    response = requests.get(
        SPOTIFY_SEARCH_URL,
        headers=headers,
        params={"q": f"artist:{artist}", "type": "artist", "limit": 5},
    )
    response.raise_for_status()
    artists = response.json()["artists"]["items"]

    return [
        {
            "source": "Spotify",
            "image_url": item["images"][0]["url"],
            "width": item["images"][0]["width"],
            "height": item["images"][0]["height"],
            "artist_name": item["name"],
            "album_name": item["name"],  # used by UI as a display label
            "type": "Artist Photo",
            "found": True,
        }
        for item in artists
        # Exact name match prevents confusingly returning unrelated artists
        if item["name"].lower() == artist.lower() and item["images"]
    ]


def _spotify_album_search(artist: str, album: str, headers: dict) -> list[ArtworkResult]:
    """Return album artwork results from Spotify for a specific album."""
    response = requests.get(
        SPOTIFY_SEARCH_URL,
        headers=headers,
        params={"q": f"artist:{artist} album:{album}", "type": "album", "limit": 5},
    )
    response.raise_for_status()
    albums = response.json()["albums"]["items"]

    return [
        {
            "source": "Spotify",
            "image_url": item["images"][0]["url"],
            "width": item["images"][0]["width"],
            "height": item["images"][0]["height"],
            "album_name": item["name"],
            # Spotify returns "single" for singles, "album" for LPs/EPs
            "type": "Single" if item.get("album_type") == "single" else "Album",
            "found": True,
        }
        for item in albums
        if item["images"]
    ]


def _spotify_track_search(artist: str, track: str, headers: dict) -> list[ArtworkResult]:
    """Return track artwork (album art) results from Spotify."""
    response = requests.get(
        SPOTIFY_SEARCH_URL,
        headers=headers,
        params={"q": f"artist:{artist} {track}", "type": "track,album", "limit": 5},
    )
    response.raise_for_status()
    tracks = response.json()["tracks"]["items"]

    return [
        {
            "source": "Spotify",
            "image_url": item["album"]["images"][0]["url"],
            "width": item["album"]["images"][0]["width"],
            "height": item["album"]["images"][0]["height"],
            "album_name": item["album"]["name"],
            "track_name": item["name"],
            "type": "Single" if item["album"].get("album_type") == "single" else "Album",
            "found": True,
        }
        for item in tracks
        if item["album"]["images"]
    ]


@st.cache_data
def search_itunes(
    artist: str,
    track: str = "",
    album: str = "",
    search_type: SearchType = "track_or_album",
) -> list[ArtworkResult]:
    """
    Search the iTunes API for artwork.

    The `track` field is also used as a fallback album name when `album` is empty,
    because iTunes search is keyword-based and either term improves relevance.

    Returns a list of result dicts (empty on failure).
    """
    # Build params based on what kind of search we're doing
    if search_type == "artist":
        params = {"term": artist, "entity": "album", "limit": 5, "sort": "popular"}
    elif search_type == "album":
        # Prefer the explicit album name; fall back to the track field
        query_title = album if album else track
        params = {"term": f"{artist} {query_title}", "entity": "album", "limit": 5}
    else:
        # "track" or "track_or_album"
        params = {"term": f"{artist} {track}", "entity": "musicTrack", "limit": 5}

    try:
        response = requests.get(ITUNES_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        raw_results = response.json().get("results", [])
    except requests.HTTPError as e:
        st.warning(f"iTunes search failed (HTTP {e.response.status_code}) for '{artist} - {track}'.")
        return []
    except Exception as e:
        st.warning(f"iTunes search error for '{artist} - {track}': {e}")
        return []

    results = []
    for item in raw_results:
        preview_url = item.get("artworkUrl100", "")
        # Replace the thumbnail resolution token with high-res equivalent
        full_res_url = preview_url.replace(ITUNES_ARTWORK_PREVIEW_SIZE, ITUNES_ARTWORK_SIZE)

        collection_name = item.get("collectionName", "").lower()
        track_name_lower = item.get("trackName", "").lower()
        # iTunes doesn't have an explicit "single" flag; we infer it when
        # the track and collection share the same name (classic single pattern)
        is_single = "single" in collection_name or track_name_lower == collection_name
        result_type = "Single" if is_single else "Album"

        results.append({
            "source": "iTunes",
            "image_url": full_res_url,
            "preview_url": preview_url,  # Small URL used for fast UI rendering
            "album_name": item.get("collectionName", "Unknown"),
            "artist_name": item.get("artistName", artist),
            "track_name": item.get("trackName", ""),
            "type": result_type,
            "found": True,
        })

    return results


@st.cache_data
def download_image(url: str) -> Optional[bytes]:
    """
    Download image bytes from a URL.
    Cached so repeated downloads of the same URL (e.g. on rerun) are free.
    Returns None on failure instead of raising, so callers handle it gracefully.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception:
        return None


# ============================================
# PARSING LAYER
# ============================================

def parse_text_entries(raw_text: str) -> list[dict]:
    """
    Parse newline-separated text entries into structured search dicts.

    Supported formats:
      "Artist"                  → artist photo search
      "Artist - Song or Album"  → track_or_album search
    """
    entries = []
    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        if " - " not in line:
            entries.append(
                {"artist": line, "track": "", "album": "", "search_type": "artist"}
            )
        else:
            # Split on first occurrence only — handles titles that contain " - "
            artist, title = line.split(" - ", maxsplit=1)
            entries.append(
                {
                    "artist": artist.strip(),
                    "track": title.strip(),
                    "album": title.strip(),
                    "search_type": "track_or_album",
                }
            )
    return entries


def parse_csv_entries(uploaded_file) -> list[dict]:
    """
    Parse an uploaded CSV into structured search dicts.
    Required column: Artist. Optional columns: Track, Album.
    Returns an empty list and surfaces an error if parsing fails.
    """
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Could not read CSV: {e}")
        return []

    if "Artist" not in df.columns:
        st.error("CSV must include an 'Artist' column.")
        return []

    entries = []
    for _, row in df.iterrows():
        artist = str(row.get("Artist", "")).strip()
        track = str(row.get("Track", "")).strip()
        album = str(row.get("Album", "")).strip()

        # pandas represents missing values as the string "nan" after str()
        track = "" if track == "nan" else track
        album = "" if album == "nan" else album

        search_type = "artist" if not track else "track_or_album"
        entries.append(
            {"artist": artist, "track": track, "album": album, "search_type": search_type}
        )

    return entries


# ============================================
# UI HELPERS
# ============================================

def build_zip(results: list[dict], selected_images: dict) -> bytes:
    """
    Package all selected artwork into a ZIP archive in memory.
    Only includes entries that have a selected URL and a successful download.
    """
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for idx, result in enumerate(results):
            selected_url = selected_images.get(idx)
            if not selected_url:
                continue
            image_bytes = download_image(selected_url)
            if not image_bytes:
                continue
            # Build a safe filename from artist + track/album
            label = result.get("track") or "artist_photo"
            filename = f"{result['artist']}_{label}.jpg".replace("/", "_")
            zf.writestr(filename, image_bytes)
    return zip_buffer.getvalue()


@st.fragment
def render_artwork_options(result_index: int, options: list[ArtworkResult]) -> None:
    """
    Render a row of artwork thumbnails with Select buttons.
    Wrapped in @st.fragment so only this widget group reruns on selection,
    not the entire page — critical for performance with many results.
    """
    num_cols = min(len(options), 5)
    cols = st.columns(max(num_cols, 3))
    current_selection = st.session_state.selected_images.get(result_index)

    for opt_idx, option in enumerate(options):
        with cols[opt_idx]:
            # Prefer preview_url (small/fast) for display; fall back to full-res
            display_url = option.get("preview_url") or option.get("image_url")
            if display_url:
                st.image(display_url, use_container_width=True)

            # Truncate long album names to keep the layout compact
            st.caption(f"{option['album_name'][:25]}...")
            st.caption(f"**{option['type']}**")

            is_selected = current_selection == option["image_url"]
            button_label = "✅ Selected" if is_selected else "Select"

            if st.button(button_label, key=f"select_{result_index}_{opt_idx}"):
                st.session_state.selected_images[result_index] = option["image_url"]
                st.rerun()


def render_download_controls(results: list[dict], key_suffix: str = "") -> None:
    """
    Render bulk ZIP download controls.
    `key_suffix` must be unique per call site to avoid Streamlit duplicate key errors.
    `results` is passed explicitly (not closed over) to keep this function portable.
    """
    selected_count = len(st.session_state.selected_images)

    if selected_count == 0:
        st.info("💡 Select artwork from the gallery to include it in your ZIP.")
        return

    st.success(f"✅ {selected_count} artworks selected. Ready to package.")
    st.download_button(
        label=f"📦 Download ZIP ({selected_count} items)",
        # build_zip is called here (lazily, on button click) rather than on every render
        data=build_zip(results, st.session_state.selected_images),
        file_name="selected_music_artwork.zip",
        mime="application/zip",
        type="primary",
        key=f"zip_download_{key_suffix}",
    )


# ============================================
# PAGE SETUP
# ============================================

st.set_page_config(
    page_title="Music Artwork Finder",
    page_icon="🎵",
    layout="wide",
)

st.title("🎵 Music Artwork Finder")
st.markdown(
    """
    **Quickly find and download high-quality music artwork.**

    Searches Spotify and iTunes APIs simultaneously. Perfect for editorial teams and content managers.

    ⚖️ **Legal Notice:** For internal editorial/operational use only. Album artwork is copyrighted
    material. Consult your legal/compliance team regarding usage rights.
    """
)
st.divider()

# Custom CSS: centers the Streamlit fullscreen button over images on hover
st.markdown(
    """
    <style>
    [data-testid="stFullScreenFrame"] button,
    [data-testid="stImage"] button {
        position: absolute !important;
        top: 50% !important; left: 50% !important;
        transform: translate(-50%, -50%) !important;
        width: 44px !important; height: 44px !important;
        background: rgba(255,255,255,0.15) !important;
        backdrop-filter: blur(4px) !important;
        border-radius: 50% !important;
        border: 1.5px solid rgba(255,255,255,0.4) !important;
        opacity: 0; transition: opacity 0.2s ease;
    }
    [data-testid="stImage"]:hover button { opacity: 1 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================
# SIDEBAR
# ============================================

with st.sidebar:
    st.header("⚙️ Settings")

    with st.expander("🔑 Spotify API Setup", expanded=False):
        st.markdown(
            "1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)\n"
            "2. Create an app and copy your credentials below:"
        )
        spotify_client_id = st.text_input(
            "Spotify Client ID",
            value=os.environ.get("SPOTIFY_CLIENT_ID", ""),
            type="password",
        )
        spotify_client_secret = st.text_input(
            "Spotify Client Secret",
            value=os.environ.get("SPOTIFY_CLIENT_SECRET", ""),
            type="password",
        )

    with st.expander("ℹ️ About This Tool", expanded=False):
        st.markdown(
            "Helps music industry professionals find and download artwork quickly.\n\n"
            "- Searches Spotify + iTunes simultaneously\n"
            "- Bulk processing via text or CSV\n"
            "- Download individually or as a ZIP\n"
            "- High-res artwork (up to 3000×3000px)"
        )

    with st.expander("⚖️ Legal Notice", expanded=False):
        st.warning("*For internal editorial/operational use only.*")
        st.markdown(
            "Images remain property of their copyright holders.\n\n"
            "✅ Internal content management  \n"
            "✅ Editorial workflow efficiency  \n"
            "❌ Commercial redistribution  \n"
            "❌ Derivative works"
        )

# ============================================
# INPUT SECTION
# ============================================

spotify_enabled = bool(spotify_client_id and spotify_client_secret)

if not spotify_enabled:
    st.warning(
        "⚠️ Add Spotify credentials in the sidebar to enable Spotify search. "
        "iTunes search works without credentials."
    )

st.subheader("📝 Input Music Entries")

tab_text, tab_csv = st.tabs(["✍️ Paste Text", "📄 Upload CSV"])
entries = []

with tab_text:
    st.markdown(
        "Paste entries one per line:\n"
        "- `Artist` → Artist photo\n"
        "- `Artist - Song` → Single/song artwork\n"
        "- `Artist - Album` → Album artwork"
    )
    raw_text = st.text_area(
        "Music Entries",
        placeholder="The All-American Rejects\nBillie Eilish - Bad Guy\nTaylor Swift - Midnights",
        height=200,
        label_visibility="collapsed",
    )
    if raw_text:
        entries = parse_text_entries(raw_text)

with tab_csv:
    st.markdown("Upload a CSV with columns: `Artist`, `Track` (required), `Album` (optional).")
    uploaded_file = st.file_uploader("Choose CSV file", type=["csv"], label_visibility="collapsed")
    if uploaded_file:
        entries = parse_csv_entries(uploaded_file)
        if entries:
            st.success(f"✅ Loaded {len(entries)} entries from CSV")

if entries:
    st.info(f"📊 Ready to search {len(entries)} entries")

# ============================================
# SEARCH EXECUTION
# ============================================

if st.button("🔍 Search for Artwork", type="primary", disabled=not entries):
    results = []
    progress_bar = st.progress(0)
    status_placeholder = st.empty()

    for i, entry in enumerate(entries):
        display_label = f"{entry['artist']} — {entry['track']}" if entry["track"] else entry["artist"]
        status_placeholder.text(f"Searching {i + 1}/{len(entries)}: {display_label}")

        spotify_results = (
            search_spotify(
                entry["artist"],
                entry["track"],
                spotify_client_id,
                spotify_client_secret,
                entry["search_type"],
                entry.get("album", ""),
            )
            if spotify_enabled
            else []
        )

        itunes_results = search_itunes(
            entry["artist"],
            entry["track"],
            entry.get("album", ""),
            entry["search_type"],
        )

        # Prefer Spotify results; fall back to iTunes if Spotify returned nothing
        combined_options = spotify_results or itunes_results
        best_result = combined_options[0] if combined_options else None

        results.append(
            {
                "artist": entry["artist"],
                "track": entry["track"],
                "album": entry.get("album", ""),
                "spotify_results": spotify_results,
                "itunes_results": itunes_results,
                "best_result": best_result,
                "options": combined_options,
            }
        )

        progress_bar.progress((i + 1) / len(entries))

    status_placeholder.empty()
    progress_bar.empty()

    st.session_state["results"] = results
    found = sum(1 for r in results if r["best_result"])
    st.success(f"✅ Search complete! Found artwork for {found} of {len(results)} entries.")

# ============================================
# RESULTS GALLERY
# ============================================

if st.session_state.get("results"):
    st.divider()
    st.subheader("📊 Results")

    if "selected_images" not in st.session_state:
        st.session_state.selected_images = {}

    results = st.session_state["results"]

    found_count = sum(1 for r in results if r.get("options"))
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Entries", len(results))
    col2.metric("Found Artwork", found_count)
    col3.metric("Not Found", len(results) - found_count)

    st.divider()
    render_download_controls(results, key_suffix="top")
    st.divider()

    for i, result in enumerate(results):
        track_label = result["track"] if result["track"] else "(Artist Search)"
        st.markdown(f"#### {i + 1}. {result['artist']} — {track_label}")

        options = result.get("options", [])
        if not options:
            st.warning("❌ No artwork found for this entry.")
        else:
            render_artwork_options(i, options)

            selected_url = st.session_state.selected_images.get(i)
            filename = f"{result['artist']}_{result.get('track') or 'artist_photo'}.jpg".replace("/", "_")

            if selected_url:
                st.download_button(
                    label="⬇️ Download Selected",
                    # download_image is @st.cache_data so this is only a real HTTP call once per URL
                    data=download_image(selected_url),
                    file_name=filename,
                    mime="image/jpeg",
                    key=f"single_download_{i}",
                )
            else:
                st.button(
                    "⬇️ Download",
                    key=f"single_download_disabled_{i}",
                    disabled=True,
                    help="Select an image above first",
                )

        st.divider()

    st.write("### 🏁 Finish Selection")
    render_download_controls(results, key_suffix="bottom")

# ============================================
# FOOTER
# ============================================

st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; font-size: 0.9em;'>"
    "Built by Rosalie Cabison | Music & Tech PM"
    "</div>",
    unsafe_allow_html=True,
)
