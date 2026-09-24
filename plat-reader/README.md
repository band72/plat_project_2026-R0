# plat-reader -- Standalone Embeddable Package

A fully encapsulated, production-ready delivery package for embedding the Cadastral Plat AI & COGO Engine into any website.

It contains both:
1. **Frontend Widget (`widget/`)**: A zero-dependency, framework-free client widget with Shadow DOM style isolation.
2. **Backend Microservice (`backend/`)**: A self-contained FastAPI server with autonomous COGO math, OCR traverse solving, and DXF/report delivery endpoints.

---

## Directory Structure

```
plat-reader/
├── widget/                           # Frontend embed assets
│   ├── plat-reader.js                # Self-mounting widget (open Shadow DOM)
│   ├── plat-reader.css               # Encapsulated styles
│   ├── index.html                    # Live test / reference host page
│   └── demo.html                     # Embed demonstration
│
├── backend/                          # Backend API Microservice
│   ├── server.py                     # Standalone FastAPI server
│   ├── requirements.txt              # Microservice Python requirements
│   ├── Dockerfile                    # Container definition (Tesseract + Poppler)
│   └── uploads/                      # Temp upload storage
│
├── engine/                           # Standalone Cadastral COGO & OCR Engine
│   ├── cogo.py                       # Coordinates, traverse math, Bowditch balancing
│   ├── cogo_block.py                 # Block solvers & MapCheck result models
│   ├── plat_pipeline.py              # OCR call-table solver & subdivision
│   ├── dxf_writer.py                 # Multi-layer DXF generator
│   └── ...                           # Full geometry suite
│
├── plat_curves/                      # Horizontal curve solvers & deflection angles
│   ├── core.py                       # Curve, PlacedCurve, DMS/bearing conversions
│   └── compound.py                   # Corner returns, fillets, concentric R/W arcs
│
├── scripts/                          # Reference & deterministic solvers
│   └── solve_block9_cogo.py          # Certified Beachwood Block 9 reference solve
│
├── sample/                           # Out-of-the-box sample plat for testing
│   └── Plat_Book_15_Page_82.pdf
│
├── docker-compose.yml                # Docker compose orchestration
├── run.sh                            # One-line local launch script
├── package.sh                        # Re-build distribution archives (.tar.gz, .zip)
└── README.md                         # This documentation
```

---

## Quickstart: Running the Backend

### Method A: Docker (Recommended for production)
Run with Docker and Docker Compose (includes system dependencies like `tesseract-ocr` and `poppler-utils`):

```bash
cd plat-reader
docker compose up --build
```
The API is now running at `http://localhost:8000`.

### Method B: Local Python
Install dependencies and run directly:

```bash
cd plat-reader
pip install -r backend/requirements.txt
./run.sh
```
Check health:
```bash
curl http://localhost:8000/health
```

---

## Embedding the Widget in Your Other Website

Copy [`widget/plat-reader.js`](file:///home/artwalk/Downloads/plat_project_2026-R0/plat-reader/widget/plat-reader.js) and [`widget/plat-reader.css`](file:///home/artwalk/Downloads/plat_project_2026-R0/plat-reader/widget/plat-reader.css) to your website or CDN, then add the following snippet to any page:

```html
<!-- 1. Mount point container -->
<div id="plat-reader"></div>

<!-- 2. Stylesheet -->
<link rel="stylesheet" href="https://your-website.com/assets/plat-reader.css">

<!-- 3. Self-mounting widget script -->
<script src="https://your-website.com/assets/plat-reader.js"
        data-api-base="https://your-plat-api.yourdomain.com"
        data-target="#plat-reader"></script>
```

### Configuration Attributes

All options are passed via `data-*` attributes on the `<script>` tag:

| Attribute | Required | Default | Meaning |
| --- | --- | --- | --- |
| `data-api-base` | **yes** | `--` | URL origin of the backend server (e.g. `https://api.yourdomain.com`). No trailing slash. |
| `data-target` | no | appends to `<body>` | CSS selector for the DOM container element. |
| `data-preset` | no | `block9` | Default dataset to solve before an upload (`block9` runs the certified reference solve). |
| `data-pob-northing` | no | `5000.00` | Northing coordinate of Point-of-Beginning. |
| `data-pob-easting` | no | `5000.00` | Easting coordinate of Point-of-Beginning. |
| `data-title` | no | `Cadastral Plat Reader` | Widget title banner text. |
| `data-css-url` | no | adjacent `plat-reader.css` | Explicit URL if the stylesheet is hosted at a different location. |

---

## Cross-Origin Resource Sharing (CORS)

The backend server allows cross-origin requests by default (`PLAT_READER_ALLOWED_ORIGINS=*`). To restrict access in production to only your websites:

```bash
export PLAT_READER_ALLOWED_ORIGINS="https://your-site.com,https://app.your-site.com"
./run.sh
```

---

## Standalone Distribution Archives

To produce standalone `.tar.gz` and `.zip` distribution bundles:

```bash
./plat-reader/package.sh
```
This generates:
- `plat-reader-standalone.tar.gz`
- `plat-reader-standalone.zip`

---

## Vision extraction (Claude) -- beta

`engine/vision_extract.py` reads printed plat values with Claude and checks them with the deterministic COGO engine:
tile the page at 300 dpi -> extract printed values per tile (strict schema, no inference) -> merge -> close each lot ->
repair loop for lots that don't close (the model can zoom the scan with `render_crop` and re-run `check_lot_closure`) ->
lots that still don't close come back `FLAGGED` for human review, never forced.

- Needs `ANTHROPIC_API_KEY` in the server environment (`pip install -r backend/requirements.txt` adds `anthropic`).
- Model: `claude-opus-5` (override with `PLAT_READER_MODEL`), with server-side refusal fallbacks enabled.
- API: `POST /api/extract` (form: `uploaded_filename`, `page`, `repair`) -> `{job_id}`; `GET /api/extract/{job_id}` -> status + result.
- Eval: `python3 eval/score_extraction.py run <plat.pdf> --page 2` scores against `eval/beachwood_sheet2_truth.json`
  (172 checked Beachwood lots). **This calls the API and costs money.** `score` re-scores a saved run offline.
- Offline tests: `pytest tests/test_vision_extract.py` (fake client, no network).

Outputs are drafting and research aids, not surveys; only a licensed surveyor can certify a boundary.
