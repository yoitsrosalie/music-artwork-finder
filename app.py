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

# ============================================
# API SEARCH FUNCTIONS
# ============================================

def search_spotify(artist, track, client_id, client_secret, search_type='track_or_album'):
    """
    Search Spotify for artwork
    search_type: 'artist', 'track', or 'track_or_album'
    Returns: dict with image_url, source, and metadata
    """
    try:
        # Get Spotify access token
        auth_url = 'https://accounts.spotify.com/api/token'
        auth_response = requests.post(auth_url, {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
        })
        auth_response.raise_for_status()
        access_token = auth_response.json()['access_token']
        
        headers = {'Authorization': f'Bearer {access_token}'}
        search_url = 'https://api.spotify.com/v1/search'
        
        # Handle artist-only search
        if search_type == 'artist':
            params = {
                'q': artist,
                'type': 'artist',
                'limit': 1
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data['artists']['items']:
                artist_data = data['artists']['items'][0]
                
                if artist_data['images']:
                    image = artist_data['images'][0]
                    return {
                        'source': 'Spotify',
                        'image_url': image['url'],
                        'width': image['width'],
                        'height': image['height'],
                        'artist_name': artist_data['name'],
                        'type': 'Artist Photo',
                        'found': True
                    }
        
        # Handle track/album search
        else:
            params = {
                'q': f'artist:{artist} track:{track}',
                'type': 'track',
                'limit': 1
            }
            
            response = requests.get(search_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data['tracks']['items']:
                track_data = data['tracks']['items'][0]
                album = track_data['album']
                
                # Get highest resolution image
                if album['images']:
                    image = album['images'][0]
                    return {
                        'source': 'Spotify',
                        'image_url': image['url'],
                        'width': image['width'],
                        'height': image['height'],
                        'album_name': album['name'],
                        'track_name': track_data['name'],
                        'type': 'Track/Album',
                        'found': True
                    }
        
        return {'found': False, 'source': 'Spotify'}
        
    except Exception as e:
        return {'found': False, 'source': 'Spotify', 'error': str(e)}


def search_itunes(artist, track='', album='', search_type='track_or_album'):
    """
    Search iTunes for artwork
    search_type: 'artist', 'track', 'album', or 'track_or_album'
    Returns: dict with image_url, source, and metadata
    """
    try:
        search_url = 'https://itunes.apple.com/search'
        
        # Artist-only search
        if search_type == 'artist':
            # Get artist's most popular album as proxy for artist image
            # (iTunes rarely returns artist photos directly, albums work better)
            params = {
                'term': artist,
                'entity': 'album',
                'limit': 1,
                'sort': 'popular'
            }
            
            response = requests.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data['results']:
                result = data['results'][0]
                artwork_url = result.get('artworkUrl100', '').replace('100x100bb', '3000x3000bb')
                
                return {
                    'source': 'iTunes',
                    'image_url': artwork_url,
                    'width': 3000,
                    'height': 3000,
                    'artist_name': result.get('artistName', artist),
                    'type': 'Artist Photo',
                    'found': True
                }
        
        # Track or Album search
        elif search_type == 'track_or_album':
            # Try as track first
            params = {
                'term': f'{artist} {track}',
                'entity': 'song',
                'limit': 1
            }
            
            response = requests.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # If track not found, try as album
            if not data['results']:
                params = {
                    'term': f'{artist} {track}',
                    'entity': 'album',
                    'limit': 1
                }
                response = requests.get(search_url, params=params)
                response.raise_for_status()
                data = response.json()
            
            if data['results']:
                result = data['results'][0]
                artwork_url = result.get('artworkUrl100', '').replace('100x100bb', '3000x3000bb')
                
                result_type = 'Track' if result.get('kind') == 'song' else 'Album'
                
                return {
                    'source': 'iTunes',
                    'image_url': artwork_url,
                    'width': 3000,
                    'height': 3000,
                    'album_name': result.get('collectionName', 'Unknown'),
                    'artist_name': result.get('artistName', artist),
                    'track_name': result.get('trackName', ''),
                    'type': result_type,
                    'found': True
                }
        
        return {'found': False, 'source': 'iTunes'}
        
    except Exception as e:
        return {'found': False, 'source': 'iTunes', 'error': str(e)}


def download_image(url):
    """Download image from URL and return bytes"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except:
        return None


# ============================================
# SIDEBAR - API CONFIGURATION
# ============================================

with st.sidebar:
    st.header("⚙️ Configuration")
    
    st.markdown("""
    ### Spotify API Setup
    1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
    2. Create an app (any name works)
    3. Copy Client ID and Client Secret below
    """)
    
    spotify_client_id = st.text_input(
        "Spotify Client ID",
        type="default",
        help="Get this from Spotify Developer Dashboard"
    )
    
    spotify_client_secret = st.text_input(
        "Spotify Client Secret",
        type="password",
        help="Get this from Spotify Developer Dashboard"
    )
    
    st.divider()
    
    st.markdown("""
    ### About
    This tool helps music industry professionals quickly find and download music artwork.
    
    **Features:**
    - Search Spotify and iTunes simultaneously
    - Bulk processing via text or CSV
    - Download individual images or all as ZIP
    - High-resolution artwork (up to 3000x3000px)
    
    **Built for:** Music industry professionals, editorial teams, and content managers
    
    ---
    
    ### ⚖️ Legal Notice
    **For internal editorial/operational use only.**
    
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
    - `Artist - Track` → Single/track artwork
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
        # Fix #1: Better progress text for artist-only searches
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
        best_result = None
        if spotify_result and spotify_result.get('found'):
            best_result = spotify_result
        elif itunes_result and itunes_result.get('found'):
            best_result = itunes_result
        
        results.append({
            'artist': entry['artist'],
            'track': entry['track'],
            'album': entry.get('album', ''),
            'spotify': spotify_result,
            'itunes': itunes_result,
            'best': best_result
        })
        
        progress_bar.progress((i + 1) / len(entries))
    
    status_text.empty()
    progress_bar.empty()
    
    # Store results in session state
    st.session_state['results'] = results
    st.success(f"✅ Search complete! Found artwork for {sum(1 for r in results if r['best'])} of {len(results)} entries")

# ============================================
# DISPLAY RESULTS
# ============================================

if 'results' in st.session_state and st.session_state['results']:
    
    st.divider()
    st.subheader("📊 Results")
    
    results = st.session_state['results']
    
    # Summary stats
    found_count = sum(1 for r in results if r['best'])
    spotify_count = sum(1 for r in results if r['spotify'] and r['spotify'].get('found'))
    itunes_count = sum(1 for r in results if r['itunes'] and r['itunes'].get('found'))
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Entries", len(results))
    col2.metric("Found Artwork", found_count)
    col3.metric("Missing Artwork", len(results) - found_count)
    
    st.divider()
    
    # Bulk download button
    if found_count > 0:
        if st.button("📦 Download All as ZIP", type="secondary"):
            with st.spinner("Creating ZIP file..."):
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                    for result in results:
                        if result['best'] and result['best'].get('image_url'):
                            img_data = download_image(result['best']['image_url'])
                            if img_data:
                                # Fix #2: Better filenames for artist photos
                                track_part = result['track'] if result['track'] else 'artist_photo'
                                filename = f"{result['artist']}_{track_part}.jpg".replace('/', '_').replace('\\', '_')
                                zip_file.writestr(filename, img_data)
                
                st.download_button(
                    label="⬇️ Download music_artwork.zip",
                    data=zip_buffer.getvalue(),
                    file_name="music_artwork.zip",
                    mime="application/zip"
                )
    
    st.divider()
    
    # Results table
    for i, result in enumerate(results):
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
            
            with col1:
                st.markdown(f"**{result['artist']}**")

            with col2:
                track_display = result['track'] if result['track'] else '(Artist Photo)'
                artwork_type = result['best'].get('type', '') if result['best'] else ''
                if artwork_type:
                    st.markdown(f"{track_display}")
                    st.caption(f"Type: {artwork_type}")
                else:
                    st.markdown(f"{track_display}")
            
            with col3:
                if result['best']:
                    st.image(result['best']['image_url'], width=100)
                    st.caption(f"Source: {result['best']['source']}")
                else:
                    st.warning("❌ Not found")
            
            with col4:
                if result['best'] and result['best'].get('image_url'):
                    img_data = download_image(result['best']['image_url'])
                    if img_data:
                        # Fix #2: Better filenames for artist photos (individual downloads)
                        track_part = result['track'] if result['track'] else 'artist_photo'
                        filename = f"{result['artist']}_{track_part}.jpg".replace('/', '_').replace('\\', '_')
                        st.download_button(
                            "⬇️ Download",
                            data=img_data,
                            file_name=filename,
                            mime="image/jpeg",
                            key=f"download_{i}"
                        )
            
            st.divider()

# ============================================
# FOOTER
# ============================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.9em;'>
Built by Rosalie Cabison | Music & Tech PM
</div>
""", unsafe_allow_html=True)
