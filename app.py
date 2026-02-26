import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import zipfile
import base64
from urllib.parse import quote

# Page config
st.set_page_config(
    page_title="Music Artwork Finder",
    page_icon="🎵",
    layout="wide"
)

# Title and description
st.title("🎵 Music Artwork Finder")
st.markdown("""
**Quickly find and download high-quality music artwork.**

This tool searches Spotify and iTunes APIs to find album, track, and artist artwork.
Perfect for music industry professionals, editorial teams, and content managers who need to source artwork efficiently.

⚖️ **Legal Notice:** For internal editorial/operational use only. Album artwork is copyrighted material owned by labels and artists. 
This tool is designed for legitimate business workflows. Consult your legal/compliance team regarding usage rights.
""")

st.divider()

st.markdown("""
<style>
/* Make the image container positioned so we can overlay the button */
[data-testid="stImage"] {
    position: relative;
    cursor: pointer;
}

/* Grab the fullscreen button and center it over the image */
[data-testid="stFullScreenFrame"] button,
[data-testid="stImage"] button {
    position: absolute !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    right: auto !important;
    bottom: auto !important;
    width: 44px !important;
    height: 44px !important;
    background: rgba(255,255,255,0.15) !important;
    backdrop-filter: blur(4px) !important;
    border-radius: 50% !important;
    border: 1.5px solid rgba(255,255,255,0.4) !important;
    opacity: 0;
    transition: opacity 0.2s ease;
}

/* Only show it on hover */
[data-testid="stImage"]:hover button {
    opacity: 1 !important;
}

</style>
""", unsafe_allow_html=True)

# ============================================
# API SEARCH FUNCTIONS
# ============================================

@st.cache_data
def get_spotify_token(client_id, client_secret):
    auth_url = 'https://accounts.spotify.com/api/token'
    auth_response = requests.post(auth_url, {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
    })
    auth_response.raise_for_status()
    return auth_response.json()['access_token']

@st.cache_data
def search_spotify(artist, track, client_id, client_secret, search_type='track_or_album', album=''):
    """
    Search Spotify for artwork
    search_type: 'artist', 'track', 'album', or 'track_or_album'
    Returns: dict with image_url, source, and metadata
    """
    try:
        # Get Spotify access token
        access_token = get_spotify_token(client_id, client_secret)
     
        headers = {'Authorization': f'Bearer {access_token}'}
        search_url = 'https://api.spotify.com/v1/search'
        
        # Handle artist-only search
        if search_type == 'artist':
            params = {
                'q': artist,
                'type': 'artist',
                'limit': 5
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            all_results = []
            for artist_data in data['artists']['items']:
                if artist_data['images']:
                    image = artist_data['images'][0]
                    all_results.append({
                        'source': 'Spotify',
                        'image_url': image['url'],
                        'width': image['width'],
                        'height': image['height'],
                        'artist_name': artist_data['name'],
                        'album_name': artist_data['name'],
                        'type': 'Artist Photo',
                        'found': True
                    })
            return all_results
            
        # SPECIFIC ALBUM search
        elif search_type == 'album':
            params = {
                'q': f'artist:{artist} album:{album}',
                'type': 'album',
                'limit': 5
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            all_results = []
            for album_data in data['albums']['items']:
                if album_data['images']:
                    image = album_data['images'][0]
                    album_type = album_data.get('album_type', 'album')
                    result_type = 'Single' if album_type == 'single' else 'Album'
                    all_results.append({
                        'source': 'Spotify',
                        'image_url': image['url'],
                        'width': image['width'],
                        'height': image['height'],
                        'album_name': album_data['name'],
                        'type': result_type,
                        'found': True
                    })
            return all_results
            
        # Handle song/album search (SONG specific or AUTO)
        else:
            params = {
                'q': f'artist:{artist} track:{track}',
                'type': 'track',
                'limit': 5
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            all_results = []
            for track_data in data['tracks']['items']:
                album_data = track_data['album']
                if album_data['images']:
                    image = album_data['images'][0]
                    album_type = album_data.get('album_type', 'album')
                    result_type = 'Single' if album_type == 'single' else 'Album'
                    all_results.append({
                        'source': 'Spotify',
                        'image_url': image['url'],
                        'width': image['width'],
                        'height': image['height'],
                        'album_name': album_data['name'],
                        'track_name': track_data['name'],
                        'type': result_type,
                        'found': True
                    })
            return all_results
        
        return []
        
    except Exception as e:
        return []


@st.cache_data
def search_itunes(artist, track='', album='', search_type='track_or_album'):
    """
    Search iTunes and return a LIST of potential artwork matches.
    """
    try:
        search_url = 'https://itunes.apple.com/search'
        all_results = []
        
        # Determine Entity and Query
        if search_type == 'artist':
            params = {'term': artist, 'entity': 'album', 'limit': 5, 'sort': 'popular'}
        elif search_type == 'track':
            params = {'term': f'{artist} {track}', 'entity': 'song', 'limit': 5}
        elif search_type == 'album':
            params = {'term': f'{artist} {album if album else track}', 'entity': 'album', 'limit': 5}
        else: # track_or_album auto logic
            query_term = track if track else album
            params = {'term': f'{artist} {query_term}', 'entity': 'musicTrack', 'limit': 5}

        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        for result in data.get('results', []):
            thumb = result.get('artworkUrl100', '')
            # High-res for download, small for the UI grid
            artwork_url = thumb.replace('100x100bb', '3000x3000bb')
            
            # Logic to detect result type
            coll_name = result.get('collectionName', '').lower()
            track_name = result.get('trackName', '').lower()
            if 'single' in coll_name or track_name == coll_name:
                result_type = 'Single'
            else:
                result_type = 'Album'

            all_results.append({
                'source': 'iTunes',
                'image_url': artwork_url,
                'preview_url': thumb, # Critical for fast UI rendering
                'album_name': result.get('collectionName', 'Unknown'),
                'artist_name': result.get('artistName', artist),
                'track_name': result.get('trackName', ''),
                'type': result_type,
                'found': True
            })
            
        return all_results # Returns a list now!
        
    except Exception as e:
        return [] # Return empty list on error


@st.cache_data
def download_image(url):
    """Download image from URL and return bytes"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except:
        return None


# ============================================
# SIDEBAR
# ============================================
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. Collapsible Spotify Config
    with st.expander("🔑 Spotify API Setup", expanded=False):
        st.markdown("""
        1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
        2. Create an app
        3. Copy credentials below:
        """)
        spotify_client_id = st.text_input("Spotify Client ID", type="password")
        spotify_client_secret = st.text_input("Spotify Client Secret", type="password")

    # 2. Collapsible About Section
    with st.expander("ℹ️ About This Tool", expanded=False):
        st.markdown("""
        ### About
        This tool helps music industry professionals quickly find and download music artwork.
    
        **Features:**
        - Search Spotify and iTunes simultaneously
        - Bulk processing via text or CSV
        - Download individual images or select multiple to download as ZIP
        - High-resolution artwork (up to 3000x3000px)
        """)

    # 3. Collapsible Legal Notice
    with st.expander("⚖️ Legal Notice", expanded=False):
        st.warning("*For internal editorial/operational use only.*")
        st.markdown("""
        Album artwork is copyrighted material. This tool is designed for legitimate business workflows - the same images you'd manually download from music platforms.
        - ✅ Internal content management
        - ✅ Editorial workflow efficiency
        - ❌ Commercial redistribution
        - ❌ Derivative works
    
        Images remain property of their copyright holders. Consult your legal team for questions about usage rights.
        """)

# ============================================
# MAIN APP - INPUT OPTIONS
# ============================================

# Check if Spotify credentials are provided
spotify_enabled = bool(spotify_client_id and spotify_client_secret)

if not spotify_enabled:
    st.warning("⚠️ Add Spotify API credentials in the sidebar to enable Spotify search. iTunes search works without credentials!")

st.subheader("📝 Input Music Entries")

# Tabs for different input methods
tab1, tab2 = st.tabs(["✍️ Paste Text", "📄 Upload CSV"])

entries = []

with tab1:
    st.markdown("""
    **Paste entries one per line:**
    - `Artist` → Artist photo
    - `Artist - Song` → Single/song artwork
    - `Artist - Album` → Album artwork
    """)
    
    entries_text = st.text_area(
        "Music Entries",
        placeholder="The All-American Rejects\nBillie Eilish - Bad Guy\nTaylor Swift - Midnights",
        height=200,
        label_visibility="collapsed"
    )
    
    if entries_text:
        for line in entries_text.strip().split('\n'):
            if line.strip():
                # Check if line contains the delimiter ' - '
                if ' - ' not in line:
                    # Just artist name → Artist photo search
                    entries.append({
                        'artist': line.strip(),
                        'track': '',
                        'album': '',
                        'search_type': 'artist'
                    })
                else:
                    # Artist - Title format → Track/Album search
                    parts = [p.strip() for p in line.split(' - ', 1)]  # Split only on first ' - '
                    if len(parts) == 2:
                        entries.append({
                            'artist': parts[0],
                            'track': parts[1],
                            'album': parts[1],
                            'search_type': 'track_or_album'
                        })

with tab2:
    st.markdown("**Upload a CSV file** with columns: `Artist`, `Track`, and optionally `Album`")
    
    uploaded_file = st.file_uploader(
        "Choose CSV file",
        type=['csv'],
        label_visibility="collapsed"
    )
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            
            # Check for required columns
            if 'Artist' in df.columns:
                for _, row in df.iterrows():
                    artist = str(row['Artist']).strip()
                    track = str(row.get('Track', '')).strip()
                    album = str(row.get('Album', '')).strip()
                    
                    # Determine search type based on Track field
                    if not track or track == 'nan':
                        search_type = 'artist'
                    else:
                        search_type = 'track_or_album'
                    
                    entries.append({
                        'artist': artist,
                        'track': track if track != 'nan' else '',
                        'album': album if album != 'nan' else '',
                        'search_type': search_type
                    })
                st.success(f"✅ Loaded {len(entries)} entries from CSV")
            else:
                st.error("❌ CSV must have 'Artist' column")
        except Exception as e:
            st.error(f"❌ Error reading CSV: {e}")

# Show entry count
if entries:
    st.info(f"📊 Ready to search {len(entries)} entries")

# ============================================
# SEARCH BUTTON AND RESULTS
# ============================================

if st.button("🔍 Search for Artwork", type="primary", disabled=len(entries) == 0):
    
    results = []
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, entry in enumerate(entries):
        # Better progress text for artist-only searches
        display_text = f"{entry['artist']} - {entry['track']}" if entry['track'] else entry['artist']
        status_text.text(f"Searching {i+1}/{len(entries)}: {display_text}")
        
        # Search both APIs
        spotify_result = None
        if spotify_enabled:
            spotify_result = search_spotify(
                entry['artist'], 
                entry['track'],
                spotify_client_id,
                spotify_client_secret,
                entry.get('search_type', 'track_or_album')
            )
        
        itunes_result = search_itunes(
            entry['artist'], 
            entry.get('track', ''), 
            entry.get('album', ''),
            entry.get('search_type', 'track_or_album')
        )
        
        # Prefer Spotify if available, fall back to iTunes
        options = spotify_result or itunes_result
        best_result = options[0] if options else None

        results.append({
            'artist': entry['artist'],
            'track': entry['track'],
            'album': entry.get('album', ''),
            'spotify': spotify_result,
            'itunes': itunes_result,
            'best': best_result,
            'options': options  # Crucial for the gallery UI to work
        })
        
        progress_bar.progress((i + 1) / len(entries))
    
    status_text.empty()
    progress_bar.empty()
    
    # Store results in session state
    st.session_state['results'] = results
    st.success(f"✅ Search complete! Found artwork for {sum(1 for r in results if r['best'])} of {len(results)} entries")

# ============================================
# DISPLAY RESULTS (Gallery Mode)
# ============================================
# 1. Add this function above your main loop
@st.fragment
def render_image_options(i, options):
    cols = st.columns(len(options))
    current_choice = st.session_state.selected_images.get(i)
    
    for opt_idx, opt in enumerate(options):
        with cols[opt_idx]:
            # Render the image and captions
            image_url = opt.get('preview_url') or opt.get('image_url') 
            if image_url:
                st.image(image_url, use_container_width=True)
            st.caption(f"{opt['album_name'][:25]}...")
            st.caption(f"**{opt['type']}**")
            
            # Selection logic
            is_selected = (current_choice == opt['image_url'])
            btn_label = "✅ Selected" if is_selected else "Select"
            
            if st.button(btn_label, key=f"select_{i}_{opt_idx}"):
                st.session_state.selected_images[i] = opt['image_url']
                # We trigger a rerun of ONLY this fragment
                st.rerun()

def render_download_ui(key_suffix=""):
    selected_count = len(st.session_state.selected_images)
    
    if selected_count > 0:
        st.success(f"✅ {selected_count} artworks selected. Ready to package.")
        
        def generate_zip():
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                for idx, result in enumerate(results):
                    selected_url = st.session_state.selected_images.get(idx)
                    if selected_url:
                        img_data = download_image(selected_url)
                        if img_data:
                            track_name = result.get('track') or 'artist_photo'
                            filename = f"{result['artist']}_{track_name}.jpg".replace('/', '_')
                            zip_file.writestr(filename, img_data)
            return zip_buffer.getvalue()

        st.download_button(
            label=f"📦 Download ZIP ({selected_count} Items)",
            data=generate_zip(),
            file_name="selected_music_artwork.zip",
            mime="application/zip",
            type="primary",
            key=f"dl_btn_{key_suffix}" # Unique key required for duplicate buttons
        )
    else:
        st.info("💡 Select artwork from the gallery to include it in your ZIP.")

if 'results' in st.session_state and st.session_state['results']:
    
    st.divider()
    st.subheader("📊 Results")
    
    # Initialize selection state if it doesn't exist
    if 'selected_images' not in st.session_state:
        st.session_state.selected_images = {}

    results = st.session_state['results']
    
    # Summary stats
    found_count = sum(1 for r in results if r.get('options'))
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Entries", len(results))
    col2.metric("Found Artwork", found_count)
    col3.metric("Missing Artwork", len(results) - found_count)
    
    st.divider()
    
     # Top Download Section
    render_download_ui(key_suffix="top")

    st.divider()
    
    # --- GALLERY GRID LOOP ---
    for i, result in enumerate(results):
        with st.container():
            st.markdown(f"#### {i+1}. {result['artist']} — {result['track'] if result['track'] else '(Artist Search)'}")
            
            options = result.get('options', [])
            
            if not options:
                st.warning("❌ No artwork found for this entry.")
            else:
                # --- 1. IMAGE SELECTION LOOP ---                
                render_image_options(i, options)

                # --- 2. FAST SINGLE DOWNLOAD ---
                # We use a lambda to delay the download until the button is clicked
                track_part = result.get('track') or 'artist_photo'
                filename = f"{result['artist']}_{track_part}.jpg".replace('/', '_')
                
                # Check if an image has been selected for this specific result
                selected_url = st.session_state.selected_images.get(i)

                if selected_url:
                    st.download_button(
                    label="⬇️ Download Selected",
                    data=download_image(selected_url), 
                    file_name=filename,
                    mime="image/jpeg",
                    key=f"dl_single_{i}"
                )
                else:
                # Optional: show a disabled button or a hint if nothing is selected yet
                    st.button("⬇️ Download", key=f"dl_disabled_{i}", disabled=True, help="Select an image first")

            st.divider()
    # Bottom Download Section
    st.write("### 🏁 Finish Selection")
    render_download_ui(key_suffix="bottom")

# ============================================
# FOOTER
# ============================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.9em;'>
Built by Rosalie Cabison | Music & Tech PM
</div>
""", unsafe_allow_html=True)
