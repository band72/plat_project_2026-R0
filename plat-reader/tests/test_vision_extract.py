"""Offline tests for engine/vision_extract.py -- a fake client stands in for the Claude API (no network, no cost)."""
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image  # noqa: E402

from engine import vision_extract as vx  # noqa: E402
from eval.score_extraction import score  # noqa: E402

# A 100' x 100' square lot, clockwise, as a surveyor would print it
SQUARE = [{"kind": "line", "bearing": b, "distance": 100.0, "radius": 0.0, "curve_tag": "", "confidence": 0.9}
          for b in ("N00°00'00\"E", "S90°00'00\"E", "S00°00'00\"E", "N90°00'00\"W")]


class FakeClient:
    """Replays scripted responses for client.beta.messages.create."""
    def __init__(self, responses):
        self.calls, self._responses = [], list(responses)
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return self._responses.pop(0)


def tool_use(name, inp, id_="tu_1"):
    return NS(type="tool_use", name=name, input=inp, id=id_)


def test_tile_image_skips_blank_and_overlaps():
    img = Image.new("L", (3000, 2000), 255)
    img.paste(0, (100, 100, 200, 200))          # ink only in the top-left
    tiles = vx.tile_image(img, page=2)
    assert len(tiles) == 1 and (tiles[0].x, tiles[0].y, tiles[0].page) == (0, 0, 2)


def test_extract_tile_parses_strict_tool_call_and_requests_fallbacks():
    lot = {"block": "15", "lot": "8", "ring_complete": True, "courses": SQUARE}
    client = FakeClient([NS(stop_reason="tool_use",
                            content=[tool_use("record_plat_values", {"lots": [lot], "curve_table": [], "line_table": []})])])
    out = vx.extract_tile(client, vx.Tile(2, 0, 0, b"png"))
    assert out["lots"][0]["lot"] == "8" and out["tile"] == {"page": 2, "x": 0, "y": 0}
    call = client.calls[0]
    assert call["model"] == vx.MODEL and call["fallbacks"] == "default"
    assert call["tools"][0]["strict"] is True


def test_extract_tile_handles_refusal():
    client = FakeClient([NS(stop_reason="refusal", content=[])])
    assert vx.extract_tile(client, vx.Tile(1, 0, 0, b"png"))["error"] == "refusal"


def test_merge_keeps_complete_ring_over_partial():
    partial = {"block": "15", "lot": "8", "ring_complete": False, "courses": SQUARE[:2]}
    full = {"block": "15", "lot": "8", "ring_complete": True, "courses": SQUARE}
    m = vx.merge_tiles([{"lots": [partial]}, {"lots": [full]}])
    assert len(m["lots"]) == 1 and m["lots"][0]["ring_complete"]


def test_check_lot_closes_and_detects_misread():
    assert vx.check_lot({"ring_complete": True, "courses": SQUARE})["status"] == "PASS"
    misread = [dict(c) for c in SQUARE]
    misread[1]["distance"] = 190.0                   # "100" read as "190"
    chk = vx.check_lot({"ring_complete": True, "courses": misread})
    assert chk["status"] == "FAIL" and abs(chk["misclosure_ft"] - 90.0) < 1e-6


def test_check_lot_uses_curve_table_chord():
    courses = [dict(c) for c in SQUARE]
    courses[1] = {"kind": "curve", "bearing": "", "distance": 0.0, "radius": 25.0, "curve_tag": "C7", "confidence": 0.9}
    ct = [{"tag": "C7", "length": 0.0, "radius": 25.0, "chord_bearing": "S90°00'00\"E", "chord": 100.0, "delta": ""}]
    assert vx.check_lot({"ring_complete": True, "courses": courses}, ct)["status"] == "PASS"


def test_repair_loop_fixes_misread_with_closure_tool(monkeypatch):
    monkeypatch.setattr(vx, "rasterize_page", lambda *a, **k: Image.new("L", (2000, 2000), 255))
    misread = [dict(c) for c in SQUARE]
    misread[1]["distance"] = 190.0
    client = FakeClient([NS(stop_reason="tool_use", content=[
        NS(type="text", text="The 190 is a 100 at 600 dpi."),
        tool_use("check_lot_closure", {"courses": SQUARE})])])
    r = vx.repair_lot(client, "x.pdf", 1, {"block": "15", "lot": "8", "ring_complete": True, "courses": misread}, [])
    assert r.check["status"] == "PASS" and r.turns == 1 and r.lot["courses"][1]["distance"] == 100.0


def test_repair_loop_flags_when_nothing_closes(monkeypatch):
    monkeypatch.setattr(vx, "rasterize_page", lambda *a, **k: Image.new("L", (2000, 2000), 255))
    misread = [dict(c) for c in SQUARE]
    misread[1]["distance"] = 190.0
    client = FakeClient([NS(stop_reason="end_turn", content=[NS(type="text", text="Printed value conflicts.")])])
    r = vx.repair_lot(client, "x.pdf", 1, {"block": "15", "lot": "8", "ring_complete": True, "courses": misread}, [])
    assert r.check["status"] == "FLAGGED"


def test_score_counts_found_and_wrong_values():
    truth = {"lots": [{"block": "15", "lot": "8", "courses": [{"distance": 100.0}] * 4},
                      {"block": "15", "lot": "9", "courses": [{"distance": 95.98}]}]}
    run = {"lots": [{"block": "15", "lot": "8", "courses": [{"distance": 100.0}, {"distance": 190.0}],
                     "check": {"status": "FAIL"}}]}
    rep = score(run, truth)
    assert rep["found"] == 1 and rep["value_precision_pct"] == 50.0
    assert rep["rows"][0]["wrong_values"] == [190.0]
