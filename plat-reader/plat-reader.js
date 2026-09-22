/**
 * plat-reader.js -- standalone embeddable widget for the Cadastral Plat AI &
 * COGO Engine. Drop this folder's two files onto any website:
 *
 *   <div id="plat-reader"></div>
 *   <script src="/path/to/plat-reader.js"
 *           data-api-base="https://your-plat-api.example.com"
 *           data-target="#plat-reader"></script>
 *
 * Design goals (see README.md for the full picture):
 *  - Self-contained: one script, one stylesheet, zero framework/build step,
 *    zero dependency on the host page's own CSS or JS.
 *  - Style-isolated: renders inside a Shadow DOM so the host site's CSS
 *    cannot leak in, and this widget's CSS cannot leak out and clobber the
 *    host site.
 *  - Cross-origin-safe downloads: the widget almost always runs on a
 *    different origin than the API it talks to, so plain `<a download>`
 *    links (which browsers silently ignore cross-origin) are never used --
 *    every download is a real fetch + blob save, with a native "Save As"
 *    dialog where the browser supports it.
 *  - Configurable, not hardcoded: every environment-specific value (API
 *    base URL, mount target, default preset) is read from the embedding
 *    script tag's `data-*` attributes, never baked into the file.
 */
(function () {
  "use strict";

  const CURRENT_SCRIPT = document.currentScript;

  function cfg(name, fallback) {
    const v = CURRENT_SCRIPT && CURRENT_SCRIPT.getAttribute(`data-${name}`);
    return v === null || v === undefined || v === "" ? fallback : v;
  }

  // ---------------------------------------------------------------------
  // Configuration (all overridable per-embed via data-* attributes on the
  // <script> tag that loads this file)
  // ---------------------------------------------------------------------
  const API_BASE = (cfg("api-base", "") || "").replace(/\/$/, "");
  const TARGET_SELECTOR = cfg("target", "");
  const DEFAULT_PRESET = cfg("preset", "block9");
  const CSS_URL = cfg("css-url", scriptRelativeUrl("plat-reader.css"));
  const TITLE = cfg("title", "Cadastral Plat Reader");
  // P.O.B. has no automatic source (a scanned image has no inherent
  // real-world coordinate system -- see IMPLEMENTATION_PLAN.md section 8),
  // so an embedder who knows their typical plat's P.O.B. convention can set
  // it once here rather than it always defaulting to the demo (5000, 5000).
  const POB_NORTHING = cfg("pob-northing", "5000.00");
  const POB_EASTING = cfg("pob-easting", "5000.00");

  if (!API_BASE) {
    console.error(
      "[plat-reader] Missing required data-api-base attribute on the " +
      "plat-reader.js <script> tag -- the widget has no backend to call " +
      "and will not mount. Example: " +
      '<script src="plat-reader.js" data-api-base="https://api.example.com">'
    );
    return;
  }

  function scriptRelativeUrl(filename) {
    try {
      return new URL(filename, CURRENT_SCRIPT.src).href;
    } catch (_e) {
      return filename;
    }
  }

  // ---------------------------------------------------------------------
  // Robust download helper (inlined so this plugin has zero external JS
  // dependencies -- kept behaviorally identical to web/static/downloads.js,
  // the shared helper used by the full app; see that file's header comment
  // for the cross-origin `download`-attribute rationale).
  // ---------------------------------------------------------------------
  function filenameFromContentDisposition(header) {
    if (!header) return null;
    const starMatch = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header);
    if (starMatch) {
      try {
        return decodeURIComponent(starMatch[1].trim().replace(/^"|"$/g, ""));
      } catch (_e) {
        /* fall through */
      }
    }
    const plainMatch = /filename="?([^";]+)"?/i.exec(header);
    return plainMatch ? plainMatch[1].trim() : null;
  }

  async function downloadFile(url, suggestedName, opts) {
    opts = opts || {};
    if (typeof opts.onStart === "function") opts.onStart();
    try {
      const useSavePicker = opts.preferPicker !== false && typeof window.showSaveFilePicker === "function";
      if (useSavePicker) {
        try {
          const handle = await window.showSaveFilePicker({ suggestedName });
          const resp = await fetch(url);
          if (!resp.ok) throw new Error(`Download failed (HTTP ${resp.status})`);
          const writable = await handle.createWritable();
          await resp.body.pipeTo(writable).catch(async () => {
            await writable.write(await resp.blob());
            await writable.close();
          });
          if (typeof opts.onDone === "function") opts.onDone("saved");
          return "saved";
        } catch (pickerErr) {
          if (pickerErr && pickerErr.name === "AbortError") {
            if (typeof opts.onDone === "function") opts.onDone("cancelled");
            return "cancelled";
          }
          // fall through to the blob-anchor fallback
        }
      }
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`Download failed (HTTP ${resp.status})`);
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filenameFromContentDisposition(resp.headers.get("Content-Disposition")) || suggestedName || "download";
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 4000);
      if (typeof opts.onDone === "function") opts.onDone("saved");
      return "saved";
    } catch (err) {
      if (typeof opts.onError === "function") opts.onError(err);
      else console.error("[plat-reader] download failed:", err);
      return "error";
    }
  }

  // ---------------------------------------------------------------------
  // Widget markup (rendered inside a Shadow DOM -- see mount() below)
  // ---------------------------------------------------------------------
  const WIDGET_HTML = `
    <div class="pr-widget">
      <div class="pr-header">
        <span class="pr-logo">&#9733;</span>
        <span class="pr-title"></span>
      </div>
      <div class="pr-note hidden" data-role="note"></div>
      <div class="pr-upload-row">
        <input type="file" class="pr-file-input" data-role="file-input" accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff" />
        <button type="button" class="pr-btn pr-btn-secondary" data-role="choose-file">Upload Plat</button>
        <span class="pr-upload-status" data-role="upload-status"></span>
      </div>
      <div class="pr-controls">
        <button type="button" class="pr-btn pr-btn-primary" data-role="run">Run Cadastral MapCheck</button>
        <span class="pr-status" data-role="status"></span>
      </div>
      <div class="pr-results hidden" data-role="results">
        <div class="pr-metrics" data-role="metrics"></div>
        <table class="pr-table" data-role="table">
          <thead>
            <tr><th>Lot</th><th>Area (SF)</th><th>Misclose</th><th>Status</th><th></th></tr>
          </thead>
          <tbody data-role="tbody"></tbody>
        </table>
        <div class="pr-downloads">
          <span class="pr-downloads-label">Deliverables:</span>
          <div class="pr-download-group" data-role="downloads"></div>
        </div>
      </div>
      <div class="pr-footer">Powered by Cadastral Plat AI &amp; COGO Engine</div>
    </div>
  `;

  // Fallback names for the native Save-As dialog, shown BEFORE the response
  // (and its real Content-Disposition filename) arrives -- see
  // downloadFile()'s picker path. Which one is right depends on which
  // analysis last ran (block9 reference vs. an uploaded plat), so
  // renderDownloadButtons() below picks per-click from `uploadedFilename`,
  // not a single static list.
  const BATCH_DOWNLOADS = [
    { type: "master_dxf", label: "Production DXF", block9Filename: "PB0030_P0082_Block9_MapCheck.dxf", customFilename: "custom_plat.dxf" },
    { type: "checksheets_dxf", label: "CheckSheets DXF", block9Filename: "PB0030_P0082_Block9_CheckSheets.dxf", customFilename: "custom_plat.dxf" },
    { type: "report_txt", label: "Report", block9Filename: "block9_mapcheck_report.txt", customFilename: "custom_plat_report.txt" },
    { type: "geojson", label: "GeoJSON", block9Filename: "block9_parcels.geojson", customFilename: "custom_plat.geojson" },
    { type: "csv", label: "CSV", block9Filename: "block9_parcels_summary.csv", customFilename: "custom_plat_summary.csv" },
  ];

  function findTarget() {
    if (TARGET_SELECTOR) {
      const el = document.querySelector(TARGET_SELECTOR);
      if (el) return el;
      console.warn(`[plat-reader] data-target "${TARGET_SELECTOR}" not found; appending to <body> instead.`);
    }
    const el = document.createElement("div");
    document.body.appendChild(el);
    return el;
  }

  async function mount() {
    const host = findTarget();
    const shadow = host.attachShadow({ mode: "open" });

    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = CSS_URL;
    shadow.appendChild(link);

    const wrap = document.createElement("div");
    wrap.innerHTML = WIDGET_HTML;
    shadow.appendChild(wrap);

    const $ = (role) => shadow.querySelector(`[data-role="${role}"]`);
    shadow.querySelector(".pr-title").textContent = TITLE;

    const runBtn = $("run");
    const statusEl = $("status");
    const noteEl = $("note");
    const resultsEl = $("results");
    const metricsEl = $("metrics");
    const tbody = $("tbody");
    const downloadsEl = $("downloads");
    const fileInput = $("file-input");
    const chooseFileBtn = $("choose-file");
    const uploadStatusEl = $("upload-status");

    // Set once a plat is successfully uploaded; drives which preset run()
    // requests. No upload yet -> DEFAULT_PRESET (normally "block9", the
    // certified reference plat) -- see README.md's Configuration table.
    let uploadedFilename = null;

    chooseFileBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      uploadedFilename = null;
      uploadStatusEl.textContent = `Uploading ${file.name}...`;
      try {
        const fd = new FormData();
        fd.append("file", file);
        const resp = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: fd });
        if (!resp.ok) {
          const body = await resp.json().catch(() => null);
          throw new Error((body && body.detail) || `Upload failed (HTTP ${resp.status})`);
        }
        const data = await resp.json();
        uploadedFilename = data.filename;
        uploadStatusEl.textContent = `${data.filename} (${data.size_kb} KB) -- ready to analyze`;
      } catch (err) {
        console.error("[plat-reader] upload failed:", err);
        uploadStatusEl.textContent = `Upload failed: ${err.message}`;
      }
    });

    function setStatus(text, isError) {
      statusEl.textContent = text || "";
      statusEl.classList.toggle("pr-status-error", !!isError);
    }

    function renderNote(note) {
      if (note) {
        noteEl.textContent = note;
        noteEl.classList.remove("hidden");
      } else {
        noteEl.classList.add("hidden");
      }
    }

    function renderMetrics(summary) {
      metricsEl.innerHTML = `
        <div class="pr-metric"><span>${summary.passed_parcels}/${summary.total_parcels}</span>Parcels Passed</div>
        <div class="pr-metric"><span>${summary.max_linear_misclose.toFixed(5)} ft</span>Max Misclose</div>
        <div class="pr-metric"><span>${summary.total_net_area_sf.toLocaleString()} SF</span>Net Area</div>
        <div class="pr-metric"><span>${summary.total_net_acres}</span>Acres</div>
      `;
    }

    function renderTable(parcels) {
      tbody.innerHTML = "";
      if (!parcels || parcels.length === 0) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="5" style="text-align: center; color: var(--pr-text-muted); padding: 16px;">No parcels extracted. See notes above.</td>`;
        tbody.appendChild(tr);
        return;
      }
      parcels.forEach((p) => {
        const tr = document.createElement("tr");
        const tier = (p.verdict ? p.verdict.split(" ")[0] : p.status).toLowerCase();
        const badgeLabel = p.verdict ? p.verdict.split(" -- ")[0] : p.status;
        const flagTip = (p.flags && p.flags.length > 0) ? ` title="${p.flags.join('; ')}"` : "";
        tr.innerHTML = `
          <td>${p.lot_id}</td>
          <td>${Math.round(p.area_sqft).toLocaleString()}</td>
          <td>${p.misclose_ft.toFixed(4)} ft</td>
          <td><span class="pr-badge pr-badge-${tier}"${flagTip}>${badgeLabel}</span></td>
          <td><button type="button" class="pr-link-btn" data-lot="${p.lot_number}">DXF</button></td>
        `;
        tr.querySelector(".pr-link-btn").addEventListener("click", (e) => {
          const btn = e.currentTarget;
          const original = btn.textContent;
          btn.textContent = "...";
          downloadFile(`${API_BASE}/api/lot_dxf/${p.lot_number}`, `Lot_${p.lot_number}_MapCheck.dxf`, {
            onDone: () => { btn.textContent = original; },
            onError: () => { btn.textContent = "Failed"; setTimeout(() => (btn.textContent = original), 1500); },
          });
        });
        tbody.appendChild(tr);
      });
    }

    function renderDownloadButtons() {
      downloadsEl.innerHTML = "";
      BATCH_DOWNLOADS.forEach((d) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pr-btn pr-btn-secondary";
        btn.textContent = d.label;
        btn.addEventListener("click", () => {
          const original = btn.textContent;
          btn.disabled = true;
          btn.textContent = "Saving...";
          const suggested = uploadedFilename ? d.customFilename : d.block9Filename;
          downloadFile(`${API_BASE}/api/download/${d.type}`, suggested, {
            onDone: () => { btn.disabled = false; btn.textContent = original; },
            onError: () => { btn.disabled = false; btn.textContent = "Failed"; setTimeout(() => (btn.textContent = original), 1500); },
          });
        });
        downloadsEl.appendChild(btn);
      });
    }
    renderDownloadButtons();

    async function run() {
      runBtn.disabled = true;
      setStatus(uploadedFilename ? "Solving uploaded plat..." : "Running cadastral MapCheck...", false);
      try {
        const formData = new FormData();
        // Once a plat is uploaded, solve IT ("custom") -- not the
        // DEFAULT_PRESET reference plat -- regardless of what DEFAULT_PRESET
        // is configured to. uploaded_filename is otherwise blank and the
        // preset falls back to DEFAULT_PRESET (normally "block9").
        formData.append("preset", uploadedFilename ? "custom" : DEFAULT_PRESET);
        if (uploadedFilename) {
          formData.append("uploaded_filename", uploadedFilename);
        }
        formData.append("pob_northing", POB_NORTHING);
        formData.append("pob_easting", POB_EASTING);
        formData.append("pi_rule_enabled", "true");
        formData.append("fac_standard", "5J-17");

        const resp = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: formData });
        if (!resp.ok) {
          const body = await resp.json().catch(() => null);
          throw new Error((body && body.detail) || `Analysis failed (HTTP ${resp.status})`);
        }
        const data = await resp.json();

        renderNote(data.note);
        renderMetrics(data.summary);
        renderTable(data.parcels);
        resultsEl.classList.remove("hidden");
        setStatus(`Done -- ${data.summary.passed_parcels}/${data.summary.total_parcels} parcels passed.`, false);
      } catch (err) {
        console.error("[plat-reader]", err);
        setStatus(err.message || "Analysis failed.", true);
      } finally {
        runBtn.disabled = false;
      }
    }

    runBtn.addEventListener("click", run);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
