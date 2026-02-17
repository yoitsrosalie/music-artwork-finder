# Music Artwork Finder

Quick tool to find and download music artwork from Spotify and iTunes APIs.

## Quick Start

1. **Get Spotify credentials:**
   - Go to https://developer.spotify.com/dashboard
   - Create an app
   - Copy Client ID and Secret

2. **Install dependencies:**
```bash
   pip install -r requirements.txt
```
   (or `pip3` on Mac)

3. **Run the app:**
```bash
   streamlit run app.py
```

4. **Use it:**
   - Enter Spotify credentials in sidebar
   - Paste songs or upload CSV
   - Click "Search for Artwork"
   - Download images!

## Test Data

Use `sample_music_entries.csv` to test - just upload it in the app.

## Format

**Text input:**
```
Artist - Track
Artist - Track - Album
```

**CSV:**
Must have columns: `Artist`, `Track` (Album is optional)

## Troubleshooting

- **"Module not found"** → Run `pip install -r requirements.txt` again
- **Spotify not working** → Check your credentials in sidebar
- **Port in use** → Close other terminals or use `--server.port 8502`

## Built With

- Streamlit (web interface)
- Spotify Web API
- iTunes Search API
```

3. **Save as:**
   - File name: `README.md`
   - Location: Inside your `music-artwork-finder` folder

---

## ✅ VERIFY YOUR FILES

Your `music-artwork-finder` folder should now have these 4 files:
```
music-artwork-finder/
├── app.py                      (the big one, ~400 lines)
├── requirements.txt            (3 lines)
├── sample_music_entries.csv    (10 songs)
└── README.md                   (quick reference)