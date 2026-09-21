import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import re

def parse_dxf_entities(dxf_path):
    lines = []
    polylines = []
    texts = []
    
    with open(dxf_path) as f:
        content = f.read().splitlines()
    
    i = 0
    while i < len(content):
        line = content[i].strip()
        if line == "0" and i + 1 < len(content):
            entity = content[i+1].strip()
            if entity == "LINE":
                # read 10, 20, 11, 21
                x1 = y1 = x2 = y2 = 0.0
                j = i + 2
                while j < len(content) and content[j].strip() != "0":
                    code = content[j].strip()
                    val = content[j+1].strip()
                    if code == "10": x1 = float(val)
                    elif code == "20": y1 = float(val)
                    elif code == "11": x2 = float(val)
                    elif code == "21": y2 = float(val)
                    j += 2
                lines.append(((x1, y1), (x2, y2)))
            elif entity == "POLYLINE":
                # read vertices until SEQEND
                v_pts = []
                j = i + 2
                while j < len(content):
                    if content[j].strip() == "0" and content[j+1].strip() == "VERTEX":
                        # read 10, 20
                        vx = vy = 0.0
                        k = j + 2
                        while k < len(content) and content[k].strip() != "0":
                            if content[k].strip() == "10": vx = float(content[k+1].strip())
                            elif content[k].strip() == "20": vy = float(content[k+1].strip())
                            k += 2
                        v_pts.append((vx, vy))
                        j = k
                    elif content[j].strip() == "0" and content[j+1].strip() == "SEQEND":
                        break
                    else:
                        j += 1
                if v_pts:
                    polylines.append(v_pts)
            elif entity == "TEXT":
                tx = ty = 0.0
                val = ""
                j = i + 2
                while j < len(content) and content[j].strip() != "0":
                    code = content[j].strip()
                    v = content[j+1].strip()
                    if code == "10": tx = float(v)
                    elif code == "20": ty = float(v)
                    elif code == "1": val = v
                    j += 2
                texts.append((tx, ty, val))
        i += 1
    return lines, polylines, texts

lines, polylines, texts = parse_dxf_entities("dxf/PB0030_P0082_Lot_Images.dxf")
print(f"Parsed: {len(lines)} lines, {len(polylines)} polylines, {len(texts)} texts")

fig, ax = plt.subplots(figsize=(16, 10), dpi=150)
ax.set_facecolor("#1e1e1e")

for p1, p2 in lines:
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color="white", lw=1.5)

for pl in polylines:
    xs = [p[0] for p in pl]
    ys = [p[1] for p in pl]
    ax.plot(xs, ys, color="cyan", lw=2.0)

for tx, ty, val in texts:
    ax.text(tx, ty, val.replace("%%d", "°"), color="yellow", fontsize=7, ha="center", va="center")

ax.set_aspect("equal")
ax.grid(True, color="#333333", linestyle="--", alpha=0.5)
ax.set_title("Beachwood Unit Two - User Lot Images CAD DXF Preview", color="white", fontsize=14)
plt.tight_layout()
plt.savefig("data/dxf_preview.png", facecolor="#1e1e1e")
print("Saved data/dxf_preview.png")
