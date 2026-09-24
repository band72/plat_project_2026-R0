import csv
import json
import math
import os
import re

# Local cache for intersection GPS coordinates. Anchored to this repo rather
# than the current working directory: a CWD-relative path made every call from
# another directory look for (and, previously, fabricate) a data/ folder there.
_GPS_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "intersection_gps_db.json",
)

# Clay County GIS master database paths
_CLAY_GIS_MASTER_PATHS = [
    "/home/artwalk/Downloads/clay/Georeferenced Output/master_all_streets_cross_reference.csv",
    "/home/artwalk/Downloads/clay/Georeferenced Output/clay_georeferenced.csv",
    "../clay/Georeferenced Output/master_all_streets_cross_reference.csv",
]

_CLAY_GIS_INDEX = None
_CLAY_CANDIDATES = None

# Street-type spellings -> one canonical token, so AVENUE == AVE and STREET == ST.
_STREET_TYPES = {
    "STREET": "ST", "ST": "ST", "AVENUE": "AVE", "AVE": "AVE", "ROAD": "RD", "RD": "RD",
    "DRIVE": "DR", "DR": "DR", "LANE": "LN", "LN": "LN", "COURT": "CT", "CT": "CT",
    "PLACE": "PL", "PL": "PL", "BOULEVARD": "BLVD", "BLVD": "BLVD", "CIRCLE": "CIR",
    "CIR": "CIR", "HIGHWAY": "HWY", "HWY": "HWY", "WAY": "WAY", "TERRACE": "TER",
    "TER": "TER", "PARKWAY": "PKWY", "PKWY": "PKWY",
}
# Directionals are part of a street's identity (EAST 8TH ST is not WEST 8TH ST).
_DIRECTIONS = {
    "N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST",
    "NE": "NORTHEAST", "NW": "NORTHWEST", "SE": "SOUTHEAST", "SW": "SOUTHWEST",
}


def _norm_street(name: str) -> tuple[tuple[str, ...], str]:
    """Canonical (name tokens, street type) for one street.

    Punctuation and case are ignored, directionals are expanded and kept as
    name tokens, and a trailing street type is canonicalised and split off
    ('' when absent) so 'Starfish Ave' and 'STARFISH AVENUE' compare equal
    while 'Starfish Court' and 'South Starfish Avenue' do not."""
    tokens = [_DIRECTIONS.get(t, t) for t in re.sub(r"[^A-Z0-9 ]", " ", str(name).upper()).split()]
    street_type = _STREET_TYPES[tokens.pop()] if tokens and tokens[-1] in _STREET_TYPES else ""
    return tuple(tokens), street_type


def _pair_match(q, c, exact: bool) -> bool:
    """Does query pair q match candidate pair c, in either street order?

    exact=True needs identical names AND street types. exact=False (the
    fallback for OCR text that lost its street type) still needs identical
    names and lets a missing type on either side act as a wildcard."""
    def same(a, b):
        return a[0] == b[0] and (a[1] == b[1] if exact else (a[1] == b[1] or not a[1] or not b[1]))
    return (same(q[0], c[0]) and same(q[1], c[1])) or (same(q[0], c[1]) and same(q[1], c[0]))


def _load_gps_db() -> list[tuple[tuple, tuple[float, float]]]:
    """Normalized ((street_a, street_b), (lat, lon)) candidates from the JSON
    cache. A missing file is an empty database: nothing is invented, and
    reading never writes. Malformed entries are skipped, not fatal."""
    if not os.path.exists(_GPS_DB_PATH):
        return []
    with open(_GPS_DB_PATH) as f:
        db = json.load(f)
    out = []
    for key, val in db.items():
        parts = key.split("&")
        try:
            lat, lon = float(val[0]), float(val[1])
        except (TypeError, ValueError, IndexError):
            continue
        if len(parts) == 2:
            out.append(((_norm_street(parts[0]), _norm_street(parts[1])), (lat, lon)))
    return out


def _load_clay_gis_index() -> dict[tuple[str, str], tuple[float, float]]:
    """Lazy loads ground-truthed intersections from the Clay County GIS master database."""
    global _CLAY_GIS_INDEX
    if _CLAY_GIS_INDEX is not None:
        return _CLAY_GIS_INDEX

    _CLAY_GIS_INDEX = {}
    for csv_path in _CLAY_GIS_MASTER_PATHS:
        if os.path.exists(csv_path):
            try:
                with open(csv_path, encoding="utf-8", errors="ignore") as f:
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


def _clay_candidates() -> list[tuple[tuple, tuple[float, float]]]:
    """Clay GIS index in the same normalized form as _load_gps_db(), built once."""
    global _CLAY_CANDIDATES
    if _CLAY_CANDIDATES is None:
        _CLAY_CANDIDATES = [((_norm_street(s1), _norm_street(s2)), gps)
                            for (s1, s2), gps in _load_clay_gis_index().items()]
    return _CLAY_CANDIDATES


def get_intersection_gps(street1: str, street2: str) -> tuple[float, float] | None:
    """
    Returns true WGS84 GPS latitude and longitude of the ground-truthed
    physical street intersection, without artificial fudging.
    Queries both local cache and Clay County GIS master georeferenced database.

    Returns None rather than a near miss. A wrong coordinate presented as
    ground truth is worse than no coordinate, so:
      1. exact match on normalized names + street types (JSON cache, then Clay GIS);
      2. else a match on names alone -- for OCR text that lost its street type --
         accepted only when it identifies exactly ONE coordinate.
    Directionals are significant, so 'West 8th St' never resolves to 'East 8th St'.
    """
    q = (_norm_street(street1), _norm_street(street2))
    if not q[0][0] or not q[1][0]:
        return None

    sources = (_load_gps_db(), _clay_candidates())
    for candidates in sources:
        for pair, gps in candidates:
            if _pair_match(q, pair, exact=True):
                return gps
    for candidates in sources:
        hits = {gps for pair, gps in candidates if _pair_match(q, pair, exact=False)}
        if len(hits) == 1:
            return hits.pop()
    return None


def add_intersection_gps(street1: str, street2: str, lat: float, lon: float):
    if os.path.exists(_GPS_DB_PATH):
        with open(_GPS_DB_PATH) as f:
            db = json.load(f)
    else:
        db = {}

    s1, s2 = sorted([street1.strip().upper(), street2.strip().upper()])
    key = f"{s1} & {s2}"
    db[key] = [lat, lon]

    os.makedirs(os.path.dirname(_GPS_DB_PATH), exist_ok=True)
    with open(_GPS_DB_PATH, 'w') as f:
        json.dump(db, f, indent=2)


def format_gps(lat: float, lon: float, places: int = 6) -> str:
    """Human-readable WGS84 pair with the hemisphere letter carrying the sign.

    Longitudes here are negative (west), so printing them with a fixed 'W'
    produced '-81.530280 W' -- a sign and a hemisphere at once."""
    return (f"{abs(lat):.{places}f}° {'N' if lat >= 0 else 'S'}, "
            f"{abs(lon):.{places}f}° {'E' if lon >= 0 else 'W'}")


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


def assert_zero_fudging(coord_a: tuple[float, float], coord_b: tuple[float, float], max_dist_ft: float = 0.05, name: str = "") -> bool:
    """Enforce Permanent Agent Rule:
    Shared ground intersections MUST share the exact same true physical GPS coordinates with zero artificial offset fudging."""
    dist_ft = haversine_distance_ft(coord_a, coord_b)
    if dist_ft > max_dist_ft:
        target_str = f" for '{name}'" if name else ""
        raise AssertionError(
            f"Zero-Fudging Violation{target_str}: Coordinates {coord_a} and {coord_b} differ by {dist_ft:.4f} ft "
            f"(exceeds zero-fudging tolerance of {max_dist_ft:.4f} ft)."
        )
    return True
