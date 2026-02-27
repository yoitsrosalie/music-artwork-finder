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

# ============================================
# TYPE ALIASES
# ============================================
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
            "album_name": item["name"],
            "type": "Artist Photo",
            "found": True,
        }
        for item in artists
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
            "type": "Single" if item.get("album_type") == "single" else "Album",
            "found": True,
        }
        for item in albums
        if item["images"]
    ]


def _spotify_track_search(artist: str, track: str, headers: dict) -> list[ArtworkResult]:
    """
    Return artwork results from Spotify for a track_or_album search.
    Collects results from both the tracks and albums sections of the response,
    then deduplicates by image URL so the same artwork isn't shown twice.
    """
    response = requests.get(
        SPOTIFY_SEARCH_URL,
        headers=headers,
        params={"q": f"artist:{artist} {track}", "type": "track,album", "limit": 5},
    )
    response.raise_for_status()
    data = response.json()

    results = []

    # Collect from tracks (returns the parent album's artwork)
    for item in data.get("tracks", {}).get("items", []):
        album = item.get("album", {})
        if album.get("images"):
            results.append({
                "source": "Spotify",
                "image_url": album["images"][0]["url"],
                "width": album["images"][0]["width"],
                "height": album["images"][0]["height"],
                "album_name": album["name"],
                "track_name": item["name"],
                "type": "Single" if album.get("album_type") == "single" else "Album",
                "found": True,
            })

    # Collect from albums (direct album matches)
    for item in data.get("albums", {}).get("items", []):
        if item.get("images"):
            results.append({
                "source": "Spotify",
                "image_url": item["images"][0]["url"],
                "width": item["images"][0]["width"],
                "height": item["images"][0]["height"],
                "album_name": item["name"],
                "track_name": "",
                "type": "Single" if item.get("album_type") == "single" else "Album",
                "found": True,
            })

    # Deduplicate by image URL — track and album results often share the same artwork
    seen = set()
    deduped = []
    for r in results:
        if r["image_url"] not in seen:
            seen.add(r["image_url"])
            deduped.append(r)

    return deduped


@st.cache_data
def search_itunes(
    artist: str,
    track: str = "",
    album: str = "",
    search_type: SearchType = "track_or_album",
) -> list[ArtworkResult]:
    """
    Search the iTunes API for artwork.

    For track_or_album searches, makes two requests — one for tracks and one for
    albums — then merges and deduplicates by image URL. iTunes does not support
    mixed entity types in a single call, so two calls are required to honour the
    "both are searched" promise in the UI.

    Returns a list of result dicts (empty on failure).
    """
    if search_type == "artist":
        param_sets = [
            {"term": artist, "entity": "album", "limit": 5, "sort": "popular"}
        ]
    elif search_type == "album":
        query_title = album if album else track
        param_sets = [
            {"term": f"{artist} {query_title}", "entity": "album", "limit": 5}
        ]
    else:
        # track_or_album: query both entity types and merge
        param_sets = [
            {"term": f"{artist} {track}", "entity": "musicTrack", "limit": 5},
            {"term": f"{artist} {track}", "entity": "album", "limit": 5},
        ]

    raw_results = []
    for params in param_sets:
        try:
            response = requests.get(ITUNES_SEARCH_URL, params=params, timeout=10)
            response.raise_for_status()
            raw_results.extend(response.json().get("results", []))
        except requests.HTTPError as e:
            st.warning(f"iTunes search failed (HTTP {e.response.status_code}) for '{artist} - {track}'.")
        except Exception as e:
            st.warning(f"iTunes search error for '{artist} - {track}': {e}")

    results = []
    seen_urls = set()

    for item in raw_results:
        preview_url = item.get("artworkUrl100", "")
        if not preview_url:
            continue
        full_res_url = preview_url.replace(ITUNES_ARTWORK_PREVIEW_SIZE, ITUNES_ARTWORK_SIZE)

        # Deduplicate by full-res URL — track and album calls often return the same artwork
        if full_res_url in seen_urls:
            continue
        seen_urls.add(full_res_url)

        collection_name = item.get("collectionName", "").lower()
        track_name_lower = item.get("trackName", "").lower()
        is_single = "single" in collection_name or track_name_lower == collection_name
        result_type = "Single" if is_single else "Album"

        results.append({
            "source": "iTunes",
            "image_url": full_res_url,
            "preview_url": preview_url,
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
    Cached so repeated downloads of the same URL are free.
    Returns None on failure instead of raising.
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

        track = "" if track == "nan" else track
        album = "" if album == "nan" else album

        search_type = "artist" if not track else "track_or_album"
        entries.append(
            {"artist": artist, "track": track, "album": album, "search_type": search_type}
        )

    return entries


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

    Searches iTunes for artwork by default. Add Spotify credentials in the sidebar to improve results and enable artist photo search.

    ⚖️ **Legal Notice:** For internal editorial/operational use only. Album artwork is copyrighted
    material. Consult your legal/compliance team regarding usage rights.
    """
)
st.divider()

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
            "- Searches Spotify and iTunes for each entry (Spotify preferred, iTunes as fallback)\n"
            "- Bulk processing via text or CSV\n"
            "- One-click download per image result\n"
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
    st.info(
        "ℹ️ Running in iTunes-only mode. Add Spotify credentials in the sidebar for better results "
        "and artist photo support."
    )

st.subheader("📝 Input Music Entries")

tab_text, tab_csv = st.tabs(["✍️ Paste Text", "📄 Upload CSV"])
entries = []

with tab_text:
    st.markdown(
        "Paste entries one per line:\n"
        "- `Artist` → Artist photo *(requires Spotify; iTunes will return albums instead)*\n"
        "- `Artist - Title` → Track or album artwork (both are searched)"
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
    st.markdown("Upload a CSV with columns: `Artist` (required), `Track` (optional), `Album` (optional). Rows without a `Track` value trigger an artist photo search *(requires Spotify; iTunes will return albums instead)*.")
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
        display_label = (
            f"{entry['artist']} — {entry['track']}"
            if entry["track"]
            else f"{entry['artist']} (artist photo)"
        )
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

@st.fragment
def render_image_options(result_index: int, result: dict, options: list[ArtworkResult]) -> None:
    """
    Render a row of artwork thumbnails with immediate one-click download buttons.
    Wrapped in @st.fragment so only this widget group reruns on interaction,
    not the entire page — critical for performance with many results.
    """
    num_cols = min(len(options), 5)
    cols = st.columns(max(num_cols, 3))

    track_part = result.get("track") or "artist_photo"

    for opt_idx, option in enumerate(options):
        with cols[opt_idx]:
            display_url = option.get("preview_url") or option.get("image_url")
            if display_url:
                st.image(display_url, use_container_width=True)

            st.caption(f"{option['album_name'][:25]}...")
            st.caption(f"**{option['type']}**")

            img_data = download_image(option.get("image_url"))
            filename = f"{result['artist']}_{track_part}_{opt_idx + 1}.jpg".replace("/", "_")

            if img_data:
                st.download_button(
                    label="⬇️ Download",
                    data=img_data,
                    file_name=filename,
                    mime="image/jpeg",
                    key=f"dl_{result_index}_{opt_idx}",
                    use_container_width=True,
                )
            else:
                st.button(
                    "⬇️ Unavailable",
                    key=f"dl_err_{result_index}_{opt_idx}",
                    disabled=True,
                    use_container_width=True,
                )


if st.session_state.get("results"):
    st.divider()
    st.subheader("📊 Results")

    results = st.session_state["results"]

    found_count = sum(1 for r in results if r.get("options"))
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Entries", len(results))
    col2.metric("Found Artwork", found_count)
    col3.metric("Not Found", len(results) - found_count)

    st.divider()

    for i, result in enumerate(results):
        track_label = result["track"] if result["track"] else "(Artist Search)"
        st.markdown(f"#### {i + 1}. {result['artist']} — {track_label}")

        options = result.get("options", [])
        if not options:
            st.warning("❌ No artwork found for this entry.")
        else:
            render_image_options(i, result, options)

        st.divider()

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
