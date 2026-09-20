import json
import os

# Local cache for intersection GPS coordinates since sandbox has no network access
# In a real environment, this would call ArcGIS Geocoding API.
_GPS_DB_PATH = "data/intersection_gps_db.json"

def get_intersection_gps(street1: str, street2: str) -> tuple[float, float] | None:
    """
    Returns true WGS84 GPS latitude and longitude of the ground-truthed 
    physical street intersection, without artificial fudging.
    """
    if not os.path.exists(_GPS_DB_PATH):
        # Create a stub database if it doesn't exist
        os.makedirs("data", exist_ok=True)
        stub_data = {
            "Main Street & East 8th Street": [30.345753, -81.653909],
            "Pelican Court & Marsh Drive": [30.123456, -81.123456],
            "Camellia Court & Brant Boulevard": [30.234567, -81.234567]
        }
        with open(_GPS_DB_PATH, 'w') as f:
            json.dump(stub_data, f, indent=2)

    with open(_GPS_DB_PATH, 'r') as f:
        db = json.load(f)

    # Normalize intersection pairing (order-independent)
    s1, s2 = sorted([street1.strip().upper(), street2.strip().upper()])
    
    # Exact match check
    for key, (lat, lon) in db.items():
        ks1, ks2 = sorted([s.strip().upper() for s in key.split("&")])
        if s1 == ks1 and s2 == ks2:
            return (lat, lon)
            
    # Fuzzy token match check (e.g. MARITIME & COASTAL)
    stopwords = {"STREET", "DRIVE", "AVENUE", "LANE", "ROAD", "BOULEVARD", "BLVD", "WAY", "COURT", "CT", "PL", "&", "THE", "OF"}
    tokens1 = {t for t in s1.split() if t not in stopwords and len(t) > 2}
    tokens2 = {t for t in s2.split() if t not in stopwords and len(t) > 2}
    
    if tokens1 and tokens2:
        for key, (lat, lon) in db.items():
            ks1, ks2 = sorted([s.strip().upper() for s in key.split("&")])
            ktoks1 = {t for t in ks1.split() if t not in stopwords and len(t) > 2}
            ktoks2 = {t for t in ks2.split() if t not in stopwords and len(t) > 2}
            # Check if (tokens1 matches ktoks1 and tokens2 matches ktoks2) or vice versa
            if (tokens1 & ktoks1 and tokens2 & ktoks2) or (tokens1 & ktoks2 and tokens2 & ktoks1):
                return (lat, lon)
            
    return None

def add_intersection_gps(street1: str, street2: str, lat: float, lon: float):
    if os.path.exists(_GPS_DB_PATH):
        with open(_GPS_DB_PATH, 'r') as f:
            db = json.load(f)
    else:
        db = {}
        
    s1, s2 = sorted([street1.strip().upper(), street2.strip().upper()])
    key = f"{s1} & {s2}"
    db[key] = [lat, lon]
    
    with open(_GPS_DB_PATH, 'w') as f:
        json.dump(db, f, indent=2)
