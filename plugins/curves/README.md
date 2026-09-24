# curves — horizontal curves for plat reading and COGO

A self-contained plugin. Nothing outside `plugins/curves/` is modified, and the package itself is stdlib-only
(`plat_curves/core.py`, `compound.py`, `plat_notation.py` never import `engine.*`). Only the audit script and
`test_engine_bridge.py` / `test_boundary_caption.py` import the engine, read-only, to compare it with the plat.

## Layout
| path | what |
|---|---|
| `plat_curves/core.py` | `Curve` (any 2 of R/Δ/L/C/T/M/E/D solve the rest), `PlacedCurve` (PC, PT, PI, RP, arc points, station table), DMS/bearing helpers |
| `plat_curves/compound.py` | concentric (R/W-edge) curves, reverse (PRC) and compound (PCC) pairs, corner returns, cul-de-sac fillets, radial/non-radial lot lines |
| `plat_curves/plat_notation.py` | parse `℄ Curve Data` text, audit a stated curve against itself, diagnose centerline-vs-R/W-edge (±30') mix-ups |
| `plat_curves/data/` | transcriptions read from the Beachwood Unit Two scans (PB30 Pg82/82A) and the boundary caption |
| `plat_curves/SPEC.md` | the contract: conventions, API, file ownership |
| `plat_curves/AUDIT_ENGINE.md`, `audit_engine_curves.py` | ranked findings on `engine/cogo_road_centerlines.py` (report only; nothing was changed there) |
| `plat_curves/REFINEMENT_LOG.md` | backlog and log for the 10-minute refinement loop |
| `docs/HORIZONTAL_CURVES.md` | teaching reference: PC/PT/PI/PRC/PCC, formulas, how plats annotate curves, failure catalogue |
| `skills/horizontal-curves-platting/` | Claude skill: the working procedure for reading/placing/auditing curves |

## Use
```bash
python3 -m pytest plugins/curves -q                      # the plugin's suite (not part of the repo-wide pytest run)
python3 plugins/curves/plat_curves/audit_engine_curves.py  # engine vs plat ℄ curve data, per curve
claude --plugin-dir plugins/curves                       # load the skill in Claude Code
```
In Python, put `plugins/curves` on `sys.path`, then `from plat_curves import Curve, PlacedCurve`.

## Conventions (see SPEC.md)
Points are `(n, e)` feet; azimuth is degrees clockwise from north; `"CW"` turns right and `"CCW"` turns left going PC→PT.
Plat reading rules: bearings and distances printed on curves are CHORD values (Sheet 2 Note 1); unlabeled radii are 25'
(Note 4); `℄ Curve Data` blocks are centerline data, and the right-of-way edge curves are concentric at R ± half the R/W width.
