"""
BP Station Daily Geocoder
Runs via GitHub Actions daily at midnight AEST.
- Fetches all BP stations in Victoria from Overpass API
- Geocodes any new/missing stations via Nominatim (server-side, no rate limit issues)
- Pushes addresses to Firebase Realtime Database
- App reads from Firebase — no Nominatim calls at runtime ever
"""

import json
import os
import time
import requests
from datetime import datetime, timezone

FIREBASE_DB_URL = os.environ.get('FIREBASE_DB_URL', '').rstrip('/')
FIREBASE_PATH   = 'geocache'

OVERPASS_URL    = 'https://overpass-api.de/api/interpreter'
NOMINATIM_URL   = 'https://nominatim.openstreetmap.org/reverse'

HEADERS_NOMINATIM = {
    'User-Agent': 'BPFuelFinder-DailyGeocoder/1.0 (github-actions; contact via github)',
    'Accept-Language': 'en',
}

# ── Fetch all BP stations in Victoria from Overpass ───────────────────────────
def fetch_vic_bp_stations():
    print("Fetching BP stations in Victoria from Overpass...")
    query = """
[out:json][timeout:60];
(
  node["amenity"="fuel"]["brand"~"^BP$",i](-39.2,140.9,-33.9,150.0);
  way["amenity"="fuel"]["brand"~"^BP$",i](-39.2,140.9,-33.9,150.0);
  node["amenity"="fuel"]["name"~"^BP",i](-39.2,140.9,-33.9,150.0);
  way["amenity"="fuel"]["name"~"^BP",i](-39.2,140.9,-33.9,150.0);
);
out center tags;
"""
    headers = {
        'User-Agent': 'BPFuelFinder-DailyGeocoder/1.0 (github-actions)',
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    mirrors = [
        'https://overpass-api.de/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter',
    ]
    for mirror in mirrors:
        try:
            print(f"  Trying {mirror}...")
            r = requests.post(mirror, data={'data': query}, headers=headers, timeout=90)
            r.raise_for_status()
            elements = r.json().get('elements', [])
            print(f"Found {len(elements)} BP stations in Victoria")
            return elements
        except Exception as e:
            print(f"  Mirror failed: {e}")
            time.sleep(3)
    raise Exception("All Overpass mirrors failed")

# ── Load existing Firebase geocache ───────────────────────────────────────────
def load_firebase_cache():
    if not FIREBASE_DB_URL:
        print("No FIREBASE_DB_URL — running without Firebase sync")
        return {}
    try:
        r = requests.get(f"{FIREBASE_DB_URL}/{FIREBASE_PATH}.json", timeout=15)
        r.raise_for_status()
        data = r.json() or {}
        # Decode Firebase keys (dots → underscores, commas → pipes)
        decoded = {}
        for k, v in data.items():
            decoded_key = k.replace('_', '.').replace('|', ',')
            decoded[decoded_key] = v
        print(f"Loaded {len(decoded)} entries from Firebase")
        return decoded
    except Exception as e:
        print(f"Firebase load failed: {e}")
        return {}

# ── Push new entries to Firebase ──────────────────────────────────────────────
def push_to_firebase(new_entries):
    if not FIREBASE_DB_URL or not new_entries:
        return
    # Encode keys for Firebase (no dots or commas allowed)
    encoded = {}
    for k, v in new_entries.items():
        encoded_key = k.replace('.', '_').replace(',', '|')
        encoded[encoded_key] = v
    try:
        r = requests.patch(
            f"{FIREBASE_DB_URL}/{FIREBASE_PATH}.json",
            json=encoded,
            timeout=30,
        )
        r.raise_for_status()
        print(f"Pushed {len(encoded)} entries to Firebase ✅")
    except Exception as e:
        print(f"Firebase push failed: {e}")

# ── Geocode a single station via Nominatim ────────────────────────────────────
def geocode_station(lat, lng, osm_id, attempt=1):
    try:
        r = requests.get(NOMINATIM_URL, params={
            'lat': lat,
            'lon': lng,
            'format': 'json',
            'zoom': 18,
            'addressdetails': 1,
        }, headers=HEADERS_NOMINATIM, timeout=15)
        r.raise_for_status()
        data = r.json()
        addr = data.get('address', {})

        house_number = addr.get('house_number', '')
        road         = addr.get('road') or addr.get('pedestrian') or addr.get('retail') or ''
        suburb       = (addr.get('suburb') or addr.get('neighbourhood') or addr.get('quarter')
                        or addr.get('town') or addr.get('village') or addr.get('city_district')
                        or addr.get('municipality') or addr.get('city') or '')
        state        = addr.get('state', '')
        postcode     = addr.get('postcode', '')

        street = ' '.join(filter(None, [house_number, road]))
        full_address = ', '.join(filter(None, [
            street,
            suburb,
            ' '.join(filter(None, [state, postcode]))
        ]))

        if not suburb:
            print(f"  ⚠ No suburb for {lat},{lng} — skipping")
            return None

        return {
            'suburb':      suburb,
            'postcode':    postcode,
            'state':       state,
            'fullAddress': full_address,
            'osmId':       osm_id,
            'ts':          int(datetime.now(timezone.utc).timestamp() * 1000),
            'source':      'github-actions-daily',
        }

    except Exception as e:
        if attempt < 3:
            wait = 2 ** attempt
            print(f"  Retry {attempt} for {lat},{lng} in {wait}s — {e}")
            time.sleep(wait)
            return geocode_station(lat, lng, osm_id, attempt + 1)
        print(f"  ✗ Failed after 3 attempts: {e}")
        return None

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== BP Station Geocoder — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===\n")

    # 1. Load existing cache from Firebase
    cache = load_firebase_cache()

    # 2. Fetch all Victoria BP stations from Overpass
    stations = fetch_vic_bp_stations()
    if not stations:
        print("No stations found — exiting")
        return

    # 3. Find stations not yet geocoded
    new_entries = {}
    skipped     = 0
    geocoded    = 0
    failed      = 0

    for s in stations:
        osm_id   = s.get('id')
        osm_type = s.get('type', 'node')
        osm_key  = f"osm_{osm_type}_{osm_id}"  # e.g. osm_node_123456789

        # Get coordinates
        lat = s.get('lat') or s.get('center', {}).get('lat')
        lng = s.get('lon') or s.get('center', {}).get('lon')
        if not lat or not lng:
            continue

        # Skip if already geocoded in Firebase (addresses don't change)
        if osm_key in cache and cache[osm_key].get('fullAddress'):
            skipped += 1
            continue

        name = s.get('tags', {}).get('name') or s.get('tags', {}).get('brand') or 'BP'
        print(f"Geocoding: {name} ({osm_type}/{osm_id}) at {lat:.4f},{lng:.4f}")

        result = geocode_station(lat, lng, osm_id)
        if result:
            new_entries[osm_key] = result
            # Also store by coord key for app backward compatibility
            coord_key = f"{float(lat):.4f},{float(lng):.4f}"
            new_entries[coord_key] = result
            geocoded += 1
            print(f"  ✅ {result['fullAddress']}")
        else:
            failed += 1

        # Respect Nominatim rate limit: 1 req/sec
        time.sleep(1.1)

    print(f"\n=== Results ===")
    print(f"  Skipped (already cached): {skipped}")
    print(f"  Newly geocoded: {geocoded}")
    print(f"  Failed: {failed}")

    # 4. Push new entries to Firebase
    if new_entries:
        push_to_firebase(new_entries)
    else:
        print("No new entries to push — Firebase already up to date ✅")

if __name__ == '__main__':
    main()
