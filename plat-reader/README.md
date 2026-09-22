# plat-reader -- embeddable plugin

A standalone, framework-free widget that drops the Cadastral Plat AI & COGO
Engine into any website: two files, one mount point, no build step.

```html
<div id="plat-reader"></div>
<link rel="stylesheet" href="https://your-cdn.example.com/plat-reader/plat-reader.css">
<script src="https://your-cdn.example.com/plat-reader/plat-reader.js"
        data-api-base="https://your-plat-api.example.com"
        data-target="#plat-reader"></script>
```

That's the whole integration. Open `index.html` in this folder for a live
example that deliberately uses a clashing host-page font/color scheme, to
demonstrate that the widget is unaffected by (and doesn't affect) the page
it's embedded in.

## What's in this folder

| File | Purpose |
| --- | --- |
| `plat-reader.js` | The whole widget: markup, styles wiring, API calls, downloads. Self-mounting, zero dependencies. |
| `plat-reader.css` | Widget styles, loaded inside a Shadow DOM (see below) so nothing leaks either direction. |
| `index.html` | A demo host page. Not required for a real embed -- for reference only. |

Only `plat-reader.js` and `plat-reader.css` need to ship to a production
site. Host them anywhere static files are served (your own site, a CDN,
object storage) -- they do **not** need to live on the same server as the
API.

## Configuration

All configuration is read from `data-*` attributes on the `<script>` tag
that loads `plat-reader.js`. Set them before the tag is inserted into the
page -- the widget reads them synchronously as soon as it loads.

| Attribute | Required | Default | Meaning |
| --- | --- | --- | --- |
| `data-api-base` | **yes** | -- | Origin of the Cadastral Plat AI & COGO Engine API, e.g. `https://api.example.com`. No trailing slash. |
| `data-target` | no | appends a new `<div>` to `<body>` | CSS selector for the element to mount into. |
| `data-preset` | no | `block9` | Dataset/preset to request when no plat has been uploaded via the widget's own "Upload Plat" button. `block9` runs the certified Beachwood Unit Two, Block 9 reference solve; once a plat is uploaded, the widget always solves *that* upload instead (`preset=custom`), regardless of this attribute. |
| `data-pob-northing` / `data-pob-easting` | no | `5000.00` / `5000.00` | Point-of-Beginning coordinates for an uploaded plat's traverse. A scanned image has no inherent real-world coordinate system (see `IMPLEMENTATION_PLAN.md` section 8) -- set these if your plats share a known P.O.B. convention. |
| `data-title` | no | `Cadastral Plat Reader` | Heading text shown in the widget. |
| `data-css-url` | no | `plat-reader.css` resolved next to `plat-reader.js` | Override if you rename or relocate the stylesheet. |

If `data-api-base` is missing, the widget logs a console error and does not
mount -- it never silently renders broken.

## Why a Shadow DOM

The widget renders inside `host.attachShadow({ mode: "open" })`, with its
own `<link rel="stylesheet">` injected inside that shadow root. That buys
two guarantees a plain namespaced `<div class="plat-reader-widget">` cannot:

- The **host page's CSS cannot reach into the widget** -- no accidental
  `button { ... }` or `* { box-sizing: ... }` from the embedding site's
  stylesheet changing how the widget looks.
- The **widget's CSS cannot leak out** onto the host page.
- `:host { all: initial; ... }` in `plat-reader.css` additionally resets the
  handful of CSS properties (font, color, line-height) that *do* inherit
  across a shadow boundary by default, so the widget looks the same
  regardless of the host page's own typography.

## Why downloads are fetch+blob, not `<a download>`

The plugin's origin (wherever you host these two files) is almost never the
same as the API's origin. Browsers silently ignore the `download` attribute
on cross-origin links -- clicking one just navigates to (or opens a viewer
for) the file instead of saving it. Every download button here instead:

1. `fetch()`s the file (a real, explicit CORS request),
2. on browsers that support the File System Access API, opens a native
   **Save As** dialog so the person can choose the destination and filename
   themselves;
3. otherwise falls back to saving the fetched bytes from a same-origin
   `blob:` URL, which always honors `download` -- guaranteeing the file
   reaches the user's computer either way.

This is the same technique used by the main app's
`web/static/downloads.js`; it's duplicated (not imported) here so this
folder has zero dependencies outside itself.

## Backend requirement: CORS

Because the widget calls `data-api-base` cross-origin, the API server must
allow it. `web/server.py` already enables this via `CORSMiddleware`,
controlled by the `PLAT_READER_ALLOWED_ORIGINS` environment variable
(comma-separated origins; defaults to `*` so the plugin works out of the
box). For production, set it to the exact origin(s) that will embed the
widget:

```bash
PLAT_READER_ALLOWED_ORIGINS=https://your-customer-site.com,https://another-site.com
```

## Local testing

`web/server.py` mounts this folder at `/plat-reader` purely as a dev
convenience (not required in production -- see above). With the API server
running locally:

```bash
python3 -m web.server
# then open http://localhost:8000/plat-reader/
```

## Scope

This widget intentionally covers the core embeddable workflow -- upload a
plat, run a MapCheck (either the uploaded plat, via
`engine/plat_pipeline.py`'s OCR-driven solver, or the `block9` reference
dataset), see summary metrics and a per-lot table with honest verdict tiers
(`PASS`/`PASS_REPAIRED`/`WATCH`/`FLAGGED`/`FAILED` -- hover a status badge
for its diagnostic notes), download every deliverable -- not the full
interactive SVG canvas, pipeline animation, per-lot checksheet modal, or
lot-count/subdivision controls from the main app at `/`. Those stay in the
main app; this plugin is meant to be small enough to drop into someone
else's page without weighing it down. Lot subdivision (`lot_count`) is
supported by the API but not exposed in this widget's UI for that reason --
pass it yourself via a custom `fetch` to `/api/analyze` if you need it.

An uploaded plat is solved exactly as honestly as the main app: OCR
reliability varies with source quality, and a difficult scan can legitimately
come back `FAILED` with the real misclosure rather than a forced success --
see `IMPLEMENTATION_PLAN.md` for why that's a deliberate design choice, not
a bug.
