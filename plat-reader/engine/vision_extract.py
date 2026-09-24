"""Vision extraction of printed plat values with Claude, checked by the deterministic COGO engine.

Pipeline (one plat page):
  1. tile_page()      rasterize at 300 dpi and cut into overlapping tiles -- whole sheets are too small to read reliably;
  2. extract_tile()   Claude reads ONLY printed values from one tile into a strict schema (no geometry, no inference);
  3. merge_tiles()    de-duplicate values seen in overlapping tiles, keep the highest-confidence reading;
  4. check_lot()      the deterministic engine closes each lot that has a complete printed ring;
  5. repair_lot()     for a lot that fails, Claude gets the residual plus two tools -- render_crop (zoom the scan) and
                      check_lot_closure (re-run the solver) -- and may correct misreads. Capped; still-failing lots are
                      returned FLAGGED for human review, never forced to close.

The API key is read by the SDK from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile).
Outputs are drafting/research aids, not surveys.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field

MODEL = os.environ.get("PLAT_READER_MODEL", "claude-opus-5")
TILE_PX = 1600
OVERLAP_PX = 240
CLOSURE_TOL_FT = 0.05

SYSTEM = (
    "You transcribe recorded subdivision plats. Report only values that are printed and legible in the image: "
    "bearings exactly as printed (e.g. N87°35'30\"E), distances in feet, curve data, and lot/block numbers. "
    "Never compute, infer or complete a value; if a digit is unclear, give your best reading with a low confidence. "
    "Bearings on curves are chord bearings."
)

EXTRACT_TOOL = {
    "name": "record_plat_values",
    "description": "Record every legible printed value in this plat tile.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["lots", "curve_table", "line_table"],
        "properties": {
            "lots": {
                "type": "array",
                "description": "One entry per lot whose number is visible, with the courses printed along its sides, "
                               "listed in order around the lot (clockwise) when the full ring is visible.",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["block", "lot", "courses", "ring_complete"],
                    "properties": {
                        "block": {"type": "string"},
                        "lot": {"type": "string"},
                        "ring_complete": {"type": "boolean",
                                          "description": "true only if every side of the lot is printed in this tile"},
                        "courses": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["kind", "bearing", "distance", "radius", "curve_tag", "confidence"],
                            "properties": {
                                "kind": {"type": "string", "enum": ["line", "curve"]},
                                "bearing": {"type": "string", "description": "as printed, or '' if not printed"},
                                "distance": {"type": "number", "description": "line length or curve arc/chord as printed; 0 if not printed"},
                                "radius": {"type": "number", "description": "curve radius as printed; 0 for lines"},
                                "curve_tag": {"type": "string", "description": "e.g. C12, or ''"},
                                "confidence": {"type": "number"},
                            },
                        }},
                    },
                },
            },
            "curve_table": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["tag", "length", "radius", "chord_bearing", "chord", "delta"],
                "properties": {"tag": {"type": "string"}, "length": {"type": "number"}, "radius": {"type": "number"},
                               "chord_bearing": {"type": "string"}, "chord": {"type": "number"}, "delta": {"type": "string"}},
            }},
            "line_table": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["tag", "bearing", "distance"],
                "properties": {"tag": {"type": "string"}, "bearing": {"type": "string"}, "distance": {"type": "number"}},
            }},
        },
    },
}


# --------------------------------------------------------------------------------------------------------------------
# 1. tiling
# --------------------------------------------------------------------------------------------------------------------
@dataclass
class Tile:
    page: int
    x: int
    y: int
    png: bytes


def rasterize_page(pdf_path: str, page: int, dpi: int = 300):
    """Page -> PIL image (poppler's pdftoppm)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with tempfile.TemporaryDirectory() as tmp:
        prefix = os.path.join(tmp, "p")
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page), "-singlefile", pdf_path, prefix],
                       check=True, capture_output=True)
        return Image.open(prefix + ".png").convert("L").copy()


def tile_image(img, page: int = 1, tile: int = TILE_PX, overlap: int = OVERLAP_PX) -> list[Tile]:
    w, h = img.size
    step = tile - overlap
    tiles = []
    for y in range(0, max(h - overlap, 1), step):
        for x in range(0, max(w - overlap, 1), step):
            crop = img.crop((x, y, min(x + tile, w), min(y + tile, h)))
            if crop.getextrema()[0] > 200:          # blank paper, nothing printed
                continue
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            tiles.append(Tile(page, x, y, buf.getvalue()))
    return tiles


# --------------------------------------------------------------------------------------------------------------------
# 2. extraction
# --------------------------------------------------------------------------------------------------------------------
def _image_block(png: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(png).decode("ascii")}}


def _create(client, **kwargs):
    """Messages call with server-side refusal fallbacks (Claude Opus 5 default)."""
    return client.beta.messages.create(model=MODEL, betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)


def extract_tile(client, tile: Tile) -> dict:
    resp = _create(
        client, max_tokens=16000, system=SYSTEM, tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": EXTRACT_TOOL["name"]},
        messages=[{"role": "user", "content": [_image_block(tile.png),
                                               {"type": "text", "text": "Transcribe this plat tile."}]}],
    )
    if resp.stop_reason == "refusal":
        return {"lots": [], "curve_table": [], "line_table": [], "error": "refusal"}
    for block in resp.content:
        if block.type == "tool_use" and block.name == EXTRACT_TOOL["name"]:
            out = dict(block.input)
            out["tile"] = {"page": tile.page, "x": tile.x, "y": tile.y}
            return out
    return {"lots": [], "curve_table": [], "line_table": [], "error": f"no tool call ({resp.stop_reason})"}


# --------------------------------------------------------------------------------------------------------------------
# 3. merge
# --------------------------------------------------------------------------------------------------------------------
def merge_tiles(results: list[dict]) -> dict:
    lots: dict[tuple[str, str], dict] = {}
    curves: dict[str, dict] = {}
    lines: dict[str, dict] = {}
    for r in results:
        for lot in r.get("lots", []):
            key = (lot["block"].strip(), lot["lot"].strip())
            prev = lots.get(key)
            score = (lot["ring_complete"], len(lot["courses"]),
                     sum(c["confidence"] for c in lot["courses"]) / max(len(lot["courses"]), 1))
            if prev is None or score > prev["_score"]:
                lots[key] = dict(lot, _score=score, tile=r.get("tile"))
        for row in r.get("curve_table", []):
            curves.setdefault(row["tag"].strip().upper(), row)
        for row in r.get("line_table", []):
            lines.setdefault(row["tag"].strip().upper(), row)
    for v in lots.values():
        v.pop("_score", None)
    return {"lots": list(lots.values()), "curve_table": list(curves.values()), "line_table": list(lines.values())}


# --------------------------------------------------------------------------------------------------------------------
# 4. deterministic check
# --------------------------------------------------------------------------------------------------------------------
def _parse_bearing(b: str) -> float | None:
    try:
        from engine.cogo import parse_bearing
        return parse_bearing(b.replace("’", "'").replace("”", '"'))
    except Exception:
        return None


def check_lot(lot: dict, curve_table: list[dict] | None = None) -> dict:
    """Close a lot ring from its printed courses. Curves use their chord (looked up in the curve table by tag when the
    chord bearing/length isn't printed on the lot). Returns misclosure, or why the lot can't be checked."""
    ct = {r["tag"].strip().upper(): r for r in (curve_table or [])}
    if not lot.get("ring_complete"):
        return {"status": "UNCHECKED", "reason": "ring not complete in the transcription"}
    n = e = perim = 0.0
    for c in lot["courses"]:
        brg, dist = c["bearing"], c["distance"]
        if c["kind"] == "curve":
            row = ct.get(c.get("curve_tag", "").strip().upper())
            if row:
                brg, dist = row["chord_bearing"], row["chord"]
        az = _parse_bearing(brg) if brg else None
        if az is None or not dist:
            return {"status": "UNCHECKED", "reason": f"missing bearing/distance on a course ({c})"}
        n += dist * math.cos(math.radians(az))
        e += dist * math.sin(math.radians(az))
        perim += dist
    mis = math.hypot(n, e)
    return {"status": "PASS" if mis <= CLOSURE_TOL_FT else "FAIL", "misclosure_ft": round(mis, 4),
            "precision": ("1:%d" % int(perim / mis)) if mis > 1e-9 else "exact"}


# --------------------------------------------------------------------------------------------------------------------
# 5. repair loop (tools: render_crop, check_lot_closure)
# --------------------------------------------------------------------------------------------------------------------
REPAIR_TOOLS = [
    {"name": "render_crop", "description": "Render a region of the plat page at high resolution to re-read small or faint text. "
                                           "Coordinates are pixels of the 300 dpi page.",
     "strict": True, "input_schema": {"type": "object", "additionalProperties": False,
                                      "required": ["x", "y", "width", "height", "dpi"],
                                      "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
                                                     "width": {"type": "integer"}, "height": {"type": "integer"},
                                                     "dpi": {"type": "integer", "enum": [300, 400, 600]}}}},
    {"name": "check_lot_closure", "description": "Re-run the deterministic closure check on a corrected course list for this lot.",
     "strict": True, "input_schema": {"type": "object", "additionalProperties": False, "required": ["courses"],
                                      "properties": {"courses": EXTRACT_TOOL["input_schema"]["properties"]["lots"]["items"]["properties"]["courses"]}}},
]


@dataclass
class RepairResult:
    lot: dict
    check: dict
    turns: int
    notes: list[str] = field(default_factory=list)


def repair_lot(client, pdf_path: str, page: int, lot: dict, curve_table: list[dict], max_turns: int = 6) -> RepairResult:
    first = check_lot(lot, curve_table)
    if first["status"] != "FAIL":
        return RepairResult(lot, first, 0)
    page_img = rasterize_page(pdf_path, page, 300)
    tile = lot.get("tile") or {"x": 0, "y": 0}
    messages = [{"role": "user", "content": [
        _image_block(_crop_png(page_img, tile["x"], tile["y"], TILE_PX, TILE_PX, 300, 300)),
        {"type": "text", "text": (
            f"Lot {lot['lot']} (block {lot['block']}) was transcribed as {json.dumps(lot['courses'])} but does not close: "
            f"{json.dumps(first)}. This tile's top-left is at page pixel ({tile['x']}, {tile['y']}). Zoom into the printed "
            "values with render_crop, correct any misread digits, and verify with check_lot_closure. Only use values you "
            "can read; if none of them fix the closure, stop and say which value you think is wrong on the plat.")}]}]
    best, turns, notes = (lot, first), 0, []
    while turns < max_turns:
        turns += 1
        resp = _create(client, max_tokens=16000, system=SYSTEM, tools=REPAIR_TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        notes += [b.text for b in resp.content if b.type == "text" and b.text.strip()]
        if resp.stop_reason != "tool_use":
            break
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            if b.name == "render_crop":
                a = b.input
                png = _crop_png(page_img, a["x"], a["y"], a["width"], a["height"], 300, a["dpi"])
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": [_image_block(png)]})
            elif b.name == "check_lot_closure":
                trial = dict(lot, courses=b.input["courses"], ring_complete=True)
                chk = check_lot(trial, curve_table)
                if chk.get("misclosure_ft", 1e9) < best[1].get("misclosure_ft", 1e9):
                    best = (trial, chk)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(chk)})
        messages.append({"role": "user", "content": results})
        if best[1]["status"] == "PASS":
            break
    final = best[1] if best[1]["status"] == "PASS" else dict(best[1], status="FLAGGED")
    return RepairResult(best[0], final, turns, notes)


def _crop_png(page_img, x, y, w, h, src_dpi, dpi) -> bytes:
    from PIL import Image
    crop = page_img.crop((x, y, x + w, y + h))
    if dpi != src_dpi:
        crop = crop.resize((int(crop.width * dpi / src_dpi), int(crop.height * dpi / src_dpi)), Image.LANCZOS)
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------------------------------------------------
def extract_pdf_page(pdf_path: str, page: int = 1, client=None, repair: bool = True) -> dict:
    """End to end for one page. Returns merged values, per-lot checks, and usage for cost tracking."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    img = rasterize_page(pdf_path, page, 300)
    tiles = tile_image(img, page)
    merged = merge_tiles([extract_tile(client, t) for t in tiles])
    checked = []
    for lot in merged["lots"]:
        if repair:
            r = repair_lot(client, pdf_path, page, lot, merged["curve_table"])
            checked.append(dict(r.lot, check=r.check, repair_turns=r.turns, repair_notes=r.notes))
        else:
            checked.append(dict(lot, check=check_lot(lot, merged["curve_table"])))
    merged["lots"] = checked
    merged["tiles"] = len(tiles)
    merged["disclaimer"] = "Drafting/research aid. Not a survey; not certified by a licensed surveyor."
    return merged
