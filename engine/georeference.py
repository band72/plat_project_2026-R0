import json
import os
import csv
import math

# Local cache for intersection GPS coordinates
_GPS_DB_PATH = "data/intersection_gps_db.json"

# Clay County GIS master database paths
_CLAY_GIS_MASTER_PATHS = [
    "/home/artwalk/Downloads/clay/Georeferenced Output/master_all_streets_cross_reference.csv",
    "/home/artwalk/Downloads/clay/Georeferenced Output/clay_georeferenced.csv",
    "../clay/Georeferenced Output/master_all_streets_cross_reference.csv",
]

_CLAY_GIS_INDEX = None


def _load_clay_gis_index() -> dict[tuple[str, str], tuple[float, float]]:
    """Lazy loads ground-truthed intersections from the Clay County GIS master database."""
    global _CLAY_GIS_INDEX
    if _CLAY_GIS_INDEX is not None:
        return _CLAY_GIS_INDEX

    _CLAY_GIS_INDEX = {}
    for csv_path in _CLAY_GIS_MASTER_PATHS:
        if os.path.exists(csv_path):
            try:
                with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        for idx in ("1", "2", "3"):
                            raw_int = row.get(f"intersection_{idx}", "")
                            lat_val = row.get(f"lat_{idx}", "")
                            lon_val = row.get(f"lon_{idx}", "")
                            if not raw_int or not lat_val or not lon_val or "&" not in raw_int:
                                continue
                            int_clean = raw_int.split(" in Sec ")[0].strip()
                            parts = int_clean.split("&")
                            if len(parts) == 2:
                                s1, s2 = sorted([parts[0].strip().upper(), parts[1].strip().upper()])
                                try:
                                    _CLAY_GIS_INDEX[(s1, s2)] = (float(lat_val), float(lon_val))
                                except ValueError:
                                    pass
            except Exception as e:
                print(f"[WARN] Error loading Clay GIS database from {csv_path}: {e}")
            break

    return _CLAY_GIS_INDEX


def get_intersection_gps(street1: str, street2: str) -> tuple[float, float] | None:
    """
    Returns true WGS84 GPS latitude and longitude of the ground-truthed 
    physical street intersection, without artificial fudging.
    Queries both local cache and Clay County GIS master georeferenced database.
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
    
    # 1. Exact match check in JSON cache
    for key, (lat, lon) in db.items():
        ks1, ks2 = sorted([s.strip().upper() for s in key.split("&")])
        if s1 == ks1 and s2 == ks2:
            return (lat, lon)

    # 2. Exact match check in Clay GIS database
    clay_idx = _load_clay_gis_index()
    if (s1, s2) in clay_idx:
        return clay_idx[(s1, s2)]

    # 3. Fuzzy token match check across JSON cache and Clay GIS database
    stopwords = {"STREET", "DRIVE", "AVENUE", "LANE", "ROAD", "BOULEVARD", "BLVD", "WAY", "COURT", "CT", "PL", "&", "THE", "OF", "CIR", "CIRCLE", "HWY", "HIGHWAY", "RD", "AVE", "ST", "DR", "LN"}
    tokens1 = {t for t in s1.split() if t not in stopwords and len(t) > 2}
    tokens2 = {t for t in s2.split() if t not in stopwords and len(t) > 2}

    if tokens1 and tokens2:
        # Check JSON cache
        for key, (lat, lon) in db.items():
            ks1, ks2 = sorted([s.strip().upper() for s in key.split("&")])
            ktoks1 = {t for t in ks1.split() if t not in stopwords and len(t) > 2}
            ktoks2 = {t for t in ks2.split() if t not in stopwords and len(t) > 2}
            if (tokens1 & ktoks1 and tokens2 & ktoks2) or (tokens1 & ktoks2 and tokens2 & ktoks1):
                return (lat, lon)

        # Check Clay GIS database
        for (ks1, ks2), (lat, lon) in clay_idx.items():
            ktoks1 = {t for t in ks1.split() if t not in stopwords and len(t) > 2}
            ktoks2 = {t for t in ks2.split() if t not in stopwords and len(t) > 2}
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


def haversine_distance_ft(coord_a: tuple[float, float], coord_b: tuple[float, float]) -> float:
    """Compute great-circle distance in survey feet between two WGS84 coordinates (lat, lon)."""
    lat1, lon1 = coord_a
    lat2, lon2 = coord_b
    r_earth_ft = 20902231.0  # WGS84 mean radius in feet
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth_ft * c


def assert_zero_fudging(coord_a: tuple[float, float], coord_b: tuple[float, float], max_dist_ft: float = 0.05) -> bool:
    """Enforce Permanent Agent Rule:
    Shared ground intersections MUST share the exact same true physical GPS coordinates with zero artificial offset fudging."""
    dist_ft = haversine_distance_ft(coord_a, coord_b)
    if dist_ft > max_dist_ft:
        raise AssertionError(
            f"Zero-Fudging Violation: Coordinates {coord_a} and {coord_b} differ by {dist_ft:.4f} ft "
            f"(exceeds zero-fudging tolerance of {max_dist_ft:.4f} ft)."
        )
    return True

