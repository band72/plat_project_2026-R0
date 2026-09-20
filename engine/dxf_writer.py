"""
dxf_writer.py -- minimal ASCII DXF (R12) writer, no external dependencies.
Written by hand because this sandbox has no network access for `pip install
ezdxf`. Supports what a plat needs: layers w/ color + linetype, LINE,
LWPOLYLINE-equivalent (POLYLINE/VERTEX/SEQEND), TEXT, POINT.

DXF R12 is a stable, widely-supported plain-text format -- opens cleanly in
AutoCAD, Carlson, BricsCAD, QGIS, etc.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# Standard AutoCAD Color Index values we use
ACI = {
    "white": 7, "red": 1, "yellow": 2, "green": 3, "cyan": 4,
    "blue": 5, "magenta": 6, "gray": 8,
}


@dataclass
class Layer:
    name: str
    color: int = 7
    linetype: str = "CONTINUOUS"


class DXFWriter:
    def __init__(self):
        self.layers: dict[str, Layer] = {}
        self.entities: list[str] = []
        self.add_layer("0", "white", "CONTINUOUS")

    def add_layer(self, name, color="white", linetype="CONTINUOUS"):
        c = ACI.get(color, color if isinstance(color, int) else 7)
        self.layers[name] = Layer(name, c, linetype)

    # ---- entities ----
    def line(self, p1, p2, layer="0"):
        self.entities.append(
            "0\nLINE\n8\n{layer}\n10\n{x1:.4f}\n20\n{y1:.4f}\n30\n0.0\n"
            "11\n{x2:.4f}\n21\n{y2:.4f}\n31\n0.0\n".format(
                layer=layer, x1=p1[1], y1=p1[0], x2=p2[1], y2=p2[0]
            )
        )  # note: DXF x=Easting, y=Northing

    def polyline(self, points, layer="0", closed=False):
        flag = 1 if closed else 0
        s = "0\nPOLYLINE\n8\n{layer}\n66\n1\n70\n{flag}\n".format(layer=layer, flag=flag)
        for p in points:
            s += "0\nVERTEX\n8\n{layer}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0.0\n".format(
                layer=layer, x=p[1], y=p[0]
            )
        s += "0\nSEQEND\n"
        self.entities.append(s)

    def arc_as_polyline(self, points, layer="CURVE"):
        self.polyline(points, layer=layer, closed=False)

    def text(self, pos, value, height=2.0, layer="TEXT-LABELS", rotation=0.0):
        self.entities.append(
            "0\nTEXT\n8\n{layer}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0.0\n"
            "40\n{h}\n1\n{val}\n50\n{rot}\n".format(
                layer=layer, x=pos[1], y=pos[0], h=height, val=value, rot=rotation
            )
        )

    def point(self, pos, layer="0"):
        self.entities.append(
            "0\nPOINT\n8\n{layer}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0.0\n".format(
                layer=layer, x=pos[1], y=pos[0]
            )
        )

    # ---- output ----
    def _header(self):
        return "0\nSECTION\n2\nHEADER\n0\nENDSEC\n"

    def _tables(self):
        s = "0\nSECTION\n2\nTABLES\n"
        s += "0\nTABLE\n2\nLTYPE\n70\n2\n"
        s += ("0\nLTYPE\n2\nCONTINUOUS\n70\n0\n3\nSolid\n72\n65\n73\n0\n40\n0.0\n")
        s += ("0\nLTYPE\n2\nDASHED\n70\n0\n3\nDashed\n72\n65\n73\n2\n40\n0.75\n"
              "49\n0.5\n74\n0\n49\n-0.25\n74\n0\n")
        s += "0\nENDTAB\n"
        s += "0\nTABLE\n2\nLAYER\n70\n{}\n".format(len(self.layers))
        for lyr in self.layers.values():
            s += "0\nLAYER\n2\n{name}\n70\n0\n62\n{color}\n6\n{lt}\n".format(
                name=lyr.name, color=lyr.color, lt=lyr.linetype
            )
        s += "0\nENDTAB\n0\nENDSEC\n"
        return s

    def _entities(self):
        return "0\nSECTION\n2\nENTITIES\n" + "".join(self.entities) + "0\nENDSEC\n"

    def save(self, path):
        with open(path, "w") as f:
            f.write(self._header())
            f.write(self._tables())
            f.write(self._entities())
            f.write("0\nEOF\n")
        return path
