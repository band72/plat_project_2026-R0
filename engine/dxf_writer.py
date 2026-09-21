"""
dxf_writer.py -- minimal ASCII DXF (R12) writer, no external dependencies.
Written by hand because this sandbox has no network access for `pip install
ezdxf`. Supports what a plat needs: layers w/ color + linetype, LINE,
LWPOLYLINE-equivalent (POLYLINE/VERTEX/SEQEND), TEXT, POINT.

DXF R12 is a stable, widely-supported plain-text format -- opens cleanly in
AutoCAD, Carlson, BricsCAD, QGIS, etc.
"""
from __future__ import annotations
import re
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
    def __init__(self, default_font: str = "Arial"):
        self.default_font = default_font
        self.layers: dict[str, Layer] = {}
        # Universal cross-platform font styles (available on all OS & CAD applications)
        self.styles: dict[str, str] = {
            "STANDARD": default_font,
            "ARIAL": "Arial",
            "ARIAL_TTF": "arial.ttf",
            "SIMPLEX": "simplex.shx",
        }
        self.entities: list[str] = []
        self.custom_linetypes: set[str] = set()
        self.add_layer("0", "white", "CONTINUOUS")

    @staticmethod
    def sanitize_layer_name(name: str) -> str:
        """Sanitize layer names to comply with standard CAD DXF conventions."""
        clean = re.sub(r'[<>\\/":;?*|=]', '_', str(name))
        return clean.strip() or "0"

    def add_style(self, name: str, font: str = "Arial"):
        """Register a custom or substitute font style in the STYLE table."""
        self.styles[name] = font

    def add_layer(self, name, color="white", linetype="CONTINUOUS"):
        clean_name = self.sanitize_layer_name(name)
        c = ACI.get(color, color if isinstance(color, int) else 7)
        self.layers[clean_name] = Layer(clean_name, c, linetype)
        return clean_name

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

    def text(self, pos, value, height=2.0, layer="TEXT-LABELS", rotation=0.0,
             halign: int = 0, valign: int = 0, style: str = "STANDARD", linetype: str = None):
        """Add TEXT entity with universal compatible font (Arial / STANDARD).
        halign: 0=Left, 1=Center, 2=Right, 4=Middle
        valign: 0=Baseline, 1=Bottom, 2=Middle, 3=Top
        style: text style name matching an entry in the STYLE table
        rotation: angle in degrees counter-clockwise from East (AutoCAD standard)
        linetype: optional linetype; if rotation != 0 and linetype is None,
                  automatically encodes ROT_{rotation:.2f} for QGIS dynamic label rotation
        """
        clean_val = str(value).replace("°", "%%d").replace("\r", "").replace("\n", " ").strip()
        layer = self.sanitize_layer_name(layer)
        rot_val = round(float(rotation), 2)
        lt_str = ""
        if linetype is not None:
            self.custom_linetypes.add(linetype)
            lt_str = f"6\n{linetype}\n"
        elif abs(rot_val) > 1e-4:
            lt = f"ROT_{rot_val:.2f}"
            self.custom_linetypes.add(lt)
            lt_str = f"6\n{lt}\n"

        s = (
            "0\nTEXT\n8\n{layer}\n{lt}7\n{style}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0.0\n"
            "40\n{h}\n1\n{val}\n50\n{rot}\n".format(
                layer=layer, lt=lt_str, style=style, x=pos[1], y=pos[0], h=height, val=clean_val, rot=rot_val
            )
        )
        if halign != 0 or valign != 0:
            s += (
                "72\n{h_align}\n11\n{x:.4f}\n21\n{y:.4f}\n31\n0.0\n73\n{v_align}\n".format(
                    h_align=halign, x=pos[1], y=pos[0], v_align=valign
                )
            )
        self.entities.append(s)

    def point(self, pos, layer="0"):
        self.entities.append(
            "0\nPOINT\n8\n{layer}\n10\n{x:.4f}\n20\n{y:.4f}\n30\n0.0\n".format(
                layer=layer, x=pos[1], y=pos[0]
            )
        )

    # ---- output ----
    def _header(self):
        return (
            "0\nSECTION\n2\nHEADER\n"
            "9\n$ACADVER\n1\nAC1009\n"
            "9\n$DWGCODEPAGE\n3\nANSI_1252\n"
            "0\nENDSEC\n"
        )

    def _tables(self):
        s = "0\nSECTION\n2\nTABLES\n"
        # 1. LTYPE table
        custom_lts = sorted(self.custom_linetypes)
        s += "0\nTABLE\n2\nLTYPE\n70\n{}\n".format(6 + len(custom_lts))
        s += "0\nLTYPE\n2\nCONTINUOUS\n70\n0\n3\nSolid\n72\n65\n73\n0\n40\n0.0\n"
        s += ("0\nLTYPE\n2\nDASHED\n70\n0\n3\nDashed\n72\n65\n73\n2\n40\n0.75\n"
              "49\n0.5\n74\n0\n49\n-0.25\n74\n0\n")
        s += ("0\nLTYPE\n2\nDASHED2\n70\n0\n3\nDashed (.5x)\n72\n65\n73\n2\n40\n0.375\n"
              "49\n0.25\n74\n0\n49\n-0.125\n74\n0\n")
        s += ("0\nLTYPE\n2\nHIDDEN\n70\n0\n3\nHidden\n72\n65\n73\n2\n40\n0.375\n"
              "49\n0.25\n74\n0\n49\n-0.125\n74\n0\n")
        s += ("0\nLTYPE\n2\nCENTER\n70\n0\n3\nCenter\n72\n65\n73\n4\n40\n2.0\n"
              "49\n1.25\n74\n0\n49\n-0.25\n74\n0\n49\n0.25\n74\n0\n49\n-0.25\n74\n0\n")
        s += ("0\nLTYPE\n2\nPHANTOM\n70\n0\n3\nPhantom\n72\n65\n73\n6\n40\n2.5\n"
              "49\n1.25\n74\n0\n49\n-0.25\n74\n0\n49\n0.25\n74\n0\n49\n-0.25\n74\n0\n"
              "49\n0.25\n74\n0\n49\n-0.25\n74\n0\n")
        for lt in custom_lts:
            s += f"0\nLTYPE\n2\n{lt}\n70\n0\n3\nSolid\n72\n65\n73\n0\n40\n0.0\n"
        s += "0\nENDTAB\n"

        # 2. LAYER table
        s += "0\nTABLE\n2\nLAYER\n70\n{}\n".format(len(self.layers))
        for lyr in self.layers.values():
            s += "0\nLAYER\n2\n{name}\n70\n0\n62\n{color}\n6\n{lt}\n".format(
                name=lyr.name, color=lyr.color, lt=lyr.linetype
            )
        s += "0\nENDTAB\n"

        # 3. STYLE table (Universally compatible TrueType font: Arial / arial.ttf)
        s += "0\nTABLE\n2\nSTYLE\n70\n{}\n".format(len(self.styles))
        for style_name, font_file in self.styles.items():
            s += (
                "0\nSTYLE\n2\n{name}\n70\n0\n40\n0.0\n41\n1.0\n50\n0.0\n"
                "71\n0\n42\n0.2\n3\n{font}\n4\n\n".format(
                    name=style_name, font=font_file
                )
            )
        s += "0\nENDTAB\n0\nENDSEC\n"
        return s

    def _entities(self):
        return "0\nSECTION\n2\nENTITIES\n" + "".join(self.entities) + "0\nENDSEC\n"

    @staticmethod
    def write_qgis_qml(path: str):
        """Write companion QGIS style file (.qml) enabling instant CAD text labeling & symbology without marker clutter."""
        qml_content = (
            "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
            "<qgis version=\"3.34.4-Prizren\" styleCategories=\"Symbology|Labeling\" labelsEnabled=\"1\">\n"
            "  <renderer-v2 type=\"embeddedSymbol\" forceraster=\"0\" enableorderby=\"0\" symbollevels=\"0\">\n"
            "    <symbols>\n"
            "      <symbol alpha=\"1\" name=\"0\" type=\"line\" clip_to_extent=\"1\" force_rhr=\"0\">\n"
            "        <layer enabled=\"1\" locked=\"0\" pass=\"0\" class=\"SimpleLine\">\n"
            "          <Option type=\"Map\">\n"
            "            <Option value=\"0\" name=\"align_dash_pattern\" type=\"QString\"/>\n"
            "            <Option value=\"square\" name=\"capstyle\" type=\"QString\"/>\n"
            "            <Option value=\"0.35\" name=\"line_width\" type=\"QString\"/>\n"
            "            <Option value=\"MM\" name=\"line_width_unit\" type=\"QString\"/>\n"
            "          </Option>\n"
            "        </layer>\n"
            "      </symbol>\n"
            "    </symbols>\n"
            "  </renderer-v2>\n"
            "  <labeling type=\"simple\">\n"
            "    <settings calloutType=\"simple\">\n"
            "      <text-style fontFamily=\"Open Sans\" fontSize=\"6.0\" fontSizeUnit=\"Point\" "
            "textColor=\"0,0,0,255\" isExpression=\"0\" fieldName=\"Text\" blendMode=\"0\">\n"
            "        <text-buffer bufferDraw=\"1\" bufferSize=\"0.6\" bufferSizeUnits=\"Point\" "
            "bufferColor=\"255,255,255,255\" bufferOpacity=\"1\"/>\n"
            "      </text-style>\n"
            "      <placement placement=\"1\" dist=\"0\" priority=\"5\" preserveRotation=\"1\"/>\n"
            "      <rendering scaleMin=\"0\" scaleMax=\"0\" obstacle=\"0\" displayAll=\"1\"/>\n"
            "      <dd_properties>\n"
            "        <Option type=\"Map\">\n"
            "          <Option value=\"\" type=\"QString\" name=\"name\"/>\n"
            "          <Option type=\"Map\" name=\"properties\">\n"
            "            <Option type=\"Map\" name=\"Halign\">\n"
            "              <Option value=\"true\" type=\"bool\" name=\"active\"/>\n"
            "              <Option value=\"'Center'\" type=\"QString\" name=\"expression\"/>\n"
            "              <Option value=\"3\" type=\"int\" name=\"type\"/>\n"
            "            </Option>\n"
            "            <Option type=\"Map\" name=\"LabelRotation\">\n"
            "              <Option value=\"true\" type=\"bool\" name=\"active\"/>\n"
            "              <Option value=\"CASE WHEN &quot;Linetype&quot; LIKE 'ROT_%' THEN -to_real(substr(&quot;Linetype&quot;, 5)) ELSE 0.0 END\" type=\"QString\" name=\"expression\"/>\n"
            "              <Option value=\"3\" type=\"int\" name=\"type\"/>\n"
            "            </Option>\n"
            "            <Option type=\"Map\" name=\"Size\">\n"
            "              <Option value=\"true\" type=\"bool\" name=\"active\"/>\n"
            "              <Option value=\"CASE WHEN &quot;Layer&quot; = 'TABLE_TEXT' THEN 4.2 WHEN &quot;Layer&quot; = 'TABLE_HEADER' THEN 5.2 WHEN &quot;Layer&quot; = 'TITLEBLOCK' THEN 7.0 WHEN &quot;Layer&quot; = 'TEXT-LABELS' THEN 5.0 ELSE 5.5 END\" type=\"QString\" name=\"expression\"/>\n"
            "              <Option value=\"3\" type=\"int\" name=\"type\"/>\n"
            "            </Option>\n"
            "          </Option>\n"
            "          <Option value=\"collection\" type=\"QString\" name=\"type\"/>\n"
            "        </Option>\n"
            "      </dd_properties>\n"
            "    </settings>\n"
            "  </labeling>\n"
            "</qgis>\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(qml_content)

    def save(self, path):
        with open(path, "w", encoding="ascii", errors="replace") as f:
            f.write(self._header())
            f.write(self._tables())
            f.write(self._entities())
            f.write("0\nEOF\n")
        # Also write companion QGIS layer style (.qml) so QGIS auto-displays CAD labels & styling
        if str(path).lower().endswith(".dxf"):
            qml_path = str(path)[:-4] + ".qml"
            self.write_qgis_qml(qml_path)
        return path
