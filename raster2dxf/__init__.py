"""raster2dxf -- convert plat/block/lot raster images (scans or rendered
mapcheck drawings) into layered, survey-convention DXF plus PNG previews.

Pipeline (see PIPELINE.md):
  preprocess  -> polarity/illumination-independent ink mask + stroke width
  linework    -> skeleton graph -> straight segments + circular arcs,
                 collinear merge, corner snapping, planarization
  text        -> text/linework separation, oriented label clusters, OCR,
                 classification (bearing / distance / curve id / curve data / lot no.)
  associate   -> labels -> parallel line pieces, curve ids -> arcs,
                 scale (ft/px) from distance labels, curve-table parse
  export      -> DXF (ezdxf R2010, NCS-style layers, true ARCs, aligned
                 labels at a uniform perpendicular offset) + PNG render + overlay
  metrics     -> ink recall/precision, association rate, scale consistency

Standalone on purpose: it only *reads* from engine/ and never edits it.
"""

__version__ = "0.1.0"
