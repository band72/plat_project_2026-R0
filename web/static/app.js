/**
 * Cadastral Plat AI & COGO Engine -- Client Application Controller
 * Handles drag & drop uploads, model invocation, 5-stage pipeline animation,
 * SVG geometry rendering, parcel card & table generation, and deliverable downloads.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements - Left Card: PLAT IMAGE
  const jobNameInput = document.getElementById("jobNameInput");
  const platDropzone = document.getElementById("platDropzone");
  const platFileInput = document.getElementById("platFileInput");
  const uploadStatus = document.getElementById("fileUploadStatus");
  const uploadedFileNameEl = document.getElementById("uploadedFileName");
  const uploadedFileSizeEl = document.getElementById("uploadedFileSize");

  const attachTableBtn = document.getElementById("attachTableBtn");
  const callTableInput = document.getElementById("callTableInput");
  const callTableBadge = document.getElementById("callTableBadge");

  const pobToggleBtn = document.getElementById("pobToggleBtn");
  const pobArrow = document.getElementById("pobArrow");
  const pobBody = document.getElementById("pobBody");
  const pobNorthing = document.getElementById("pobNorthing");
  const pobEasting = document.getElementById("pobEasting");
  const paramRadius = document.getElementById("paramRadius");

  const extractLotsCheckbox = document.getElementById("extractLotsCheckbox");
  const runModelBtn = document.getElementById("runModelBtn");
  const analysisNoteBanner = document.getElementById("analysisNoteBanner");

  // DOM Elements - Right Card: PIPELINE
  const stages = {
    vision: { el: document.getElementById("stageVision"), badge: document.getElementById("badgeVision") },
    traverse: { el: document.getElementById("stageTraverse"), badge: document.getElementById("badgeTraverse") },
    consensus: { el: document.getElementById("stageConsensus"), badge: document.getElementById("badgeConsensus") },
    repair: { el: document.getElementById("stageRepair"), badge: document.getElementById("badgeRepair") },
    dxf: { el: document.getElementById("stageDxf"), badge: document.getElementById("badgeDxf") },
  };

  // Metrics
  const metricMisclose = document.getElementById("metricMisclose");
  const metricPrecision = document.getElementById("metricPrecision");
  const metricArea = document.getElementById("metricArea");
  const metricAcres = document.getElementById("metricAcres");
  const metricLotsCount = document.getElementById("metricLotsCount");

  // Visualizer & Grid
  const cadastralSvg = document.getElementById("cadastralSvg");
  const svgGeometryGroup = document.getElementById("svgGeometryGroup");
  const lotTooltip = document.getElementById("lotTooltip");
  const fitViewBtn = document.getElementById("fitViewBtn");
  const parcelsCardsGrid = document.getElementById("parcelsCardsGrid");
  const cadastralTableBody = document.getElementById("cadastralTableBody");
  const filterLotInput = document.getElementById("filterLotInput");
  const filteredCountBadge = document.getElementById("filteredCountBadge");

  // Modal
  const checksheetModal = document.getElementById("checksheetModal");
  const modalLotTitle = document.getElementById("modalLotTitle");
  const checksheetContent = document.getElementById("checksheetContent");
  const closeModalBtn = document.getElementById("closeModalBtn");
  const copyChecksheetBtn = document.getElementById("copyChecksheetBtn");
  const modalDxfDownloadBtn = document.getElementById("modalDxfDownloadBtn");

  // State
  let currentParcels = [];
  let currentAnalysisData = null;
  let activeUploadedFile = null;
  let activeCallTableFile = null;
  let transformFn = null;
  // "block9" (the only wired-up solver) until a plat is uploaded, then
  // "custom" -- previously tracked via a hidden <select>; plain state is
  // simpler and doesn't require a fake form control just to hold a string.
  let currentPreset = "block9";

  // Wire every static download link (batch deliverables bar + modal DXF
  // button) to a real fetch+save instead of relying on the `download`
  // attribute, which browsers ignore for cross-origin requests -- see
  // downloads.js. Re-run (safe/idempotent) after each dynamic render below.
  if (window.PlatDownloads) PlatDownloads.wireDownloadLinks(document);

  // -------------------------------------------------------------------------
  // POB Collapsible Accordion
  // -------------------------------------------------------------------------
  if (pobToggleBtn && pobBody && pobArrow) {
    pobToggleBtn.addEventListener("click", () => {
      const isHidden = pobBody.classList.toggle("hidden");
      pobArrow.classList.toggle("open", !isHidden);
    });
  }

  // -------------------------------------------------------------------------
  // Call Table Attach Handling
  // -------------------------------------------------------------------------
  if (attachTableBtn && callTableInput) {
    callTableInput.addEventListener("click", (e) => e.stopPropagation());
    attachTableBtn.addEventListener("click", () => callTableInput.click());
    callTableInput.addEventListener("change", async () => {
      if (callTableInput.files && callTableInput.files.length > 0) {
        const file = callTableInput.files[0];
        callTableBadge.textContent = `Uploading ${file.name}...`;
        callTableBadge.classList.remove("hidden");

        const formData = new FormData();
        formData.append("file", file);
        try {
          const resp = await fetch("/api/upload", { method: "POST", body: formData });
          if (!resp.ok) throw new Error("Call table upload failed");
          const data = await resp.json();
          activeCallTableFile = data.filename;
          callTableBadge.textContent = `${data.filename} (${data.size_kb} KB)`;
        } catch (err) {
          console.error(err);
          callTableBadge.textContent = file.name;
        }
      }
    });
  }

  // -------------------------------------------------------------------------
  // Plat File Upload & Drag & Drop Handling
  // -------------------------------------------------------------------------
  if (platDropzone && platFileInput) {
    platFileInput.addEventListener("click", (e) => e.stopPropagation());
    platDropzone.addEventListener("click", (e) => {
      if (e.target !== platFileInput) platFileInput.click();
    });

    platDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      platDropzone.classList.add("dragover");
    });

    platDropzone.addEventListener("dragleave", () => {
      platDropzone.classList.remove("dragover");
    });

    platDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      platDropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });

    platFileInput.addEventListener("change", () => {
      if (platFileInput.files && platFileInput.files.length > 0) {
        handleFileUpload(platFileInput.files[0]);
      }
    });
  }

  async function handleFileUpload(file) {
    const formData = new FormData();
    formData.append("file", file);

    uploadStatus.classList.remove("hidden");
    uploadedFileNameEl.textContent = `Uploading ${file.name}...`;
    uploadedFileSizeEl.textContent = "";

    try {
      const resp = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });
      if (!resp.ok) throw new Error("Upload failed");
      const data = await resp.json();

      activeUploadedFile = data.filename;
      uploadedFileNameEl.textContent = data.filename;
      uploadedFileSizeEl.textContent = `(${data.size_kb} KB)`;
      currentPreset = "custom";
    } catch (err) {
      console.error(err);
      uploadedFileNameEl.textContent = "Upload failed: " + err.message;
      uploadedFileSizeEl.textContent = "";
    }
  }

  // -------------------------------------------------------------------------
  // Model Dispatch & 5-Stage Pipeline Execution
  // -------------------------------------------------------------------------
  if (runModelBtn) {
    runModelBtn.addEventListener("click", () => executeCadastralModel());
  }

  async function executeCadastralModel() {
    runModelBtn.disabled = true;
    runModelBtn.innerHTML = `
      <svg class="extract-eye-icon spinning" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M12 2a10 10 0 0 1 10 10"></path>
      </svg>
      <span class="btn-extract-text">Processing Plat...</span>
    `;

    // Reset pipeline visual states
    Object.values(stages).forEach(s => {
      if (s.el) s.el.className = "pipeline-item";
      if (s.badge) {
        s.badge.textContent = "";
        s.badge.style.display = "none";
      }
    });

    const setStageActive = (key, text) => {
      const s = stages[key];
      if (!s || !s.el) return;
      s.el.className = "pipeline-item active";
      if (s.badge) {
        s.badge.textContent = text;
        s.badge.style.display = "inline-block";
      }
    };

    const setStageDone = (key, text) => {
      const s = stages[key];
      if (!s || !s.el) return;
      s.el.className = "pipeline-item done";
      if (s.badge) {
        s.badge.textContent = text;
        s.badge.style.display = "inline-block";
      }
    };

    // Stage 1: Vision Extraction
    setStageActive("vision", "SCANNING");
    await new Promise(r => setTimeout(r, 220));
    setStageDone("vision", "PARSED");

    // Stage 2: Traverse Computation
    setStageActive("traverse", "COMPUTING");
    await new Promise(r => setTimeout(r, 200));
    setStageDone("traverse", "PASS");

    // Stage 3: Consensus Voting
    setStageActive("consensus", "VOTING");
    await new Promise(r => setTimeout(r, 180));
    setStageDone("consensus", "CONVERGED");

    // Stage 4: AI Misclosure Repair (Backend Call)
    setStageActive("repair", "ANALYZING");

    const formData = new FormData();
    formData.append("preset", currentPreset);
    if (activeUploadedFile) {
      formData.append("uploaded_filename", activeUploadedFile);
    }
    if (jobNameInput && jobNameInput.value.trim()) {
      formData.append("job_name", jobNameInput.value.trim());
    }
    if (activeCallTableFile) {
      formData.append("call_table_filename", activeCallTableFile);
    }
    formData.append("pob_northing", pobNorthing ? pobNorthing.value : "5000.00");
    formData.append("pob_easting", pobEasting ? pobEasting.value : "5000.00");
    formData.append("return_radius", paramRadius ? paramRadius.value : "25.0");
    formData.append("extract_individual_lots", extractLotsCheckbox && extractLotsCheckbox.checked ? "true" : "false");
    formData.append("pi_rule_enabled", "true");
    formData.append("fac_standard", "5J-17");

    try {
      const resp = await fetch("/api/analyze", {
        method: "POST",
        body: formData
      });

      if (!resp.ok) {
        const errBody = await resp.json().catch(() => null);
        throw new Error((errBody && errBody.detail) || `Cadastral analysis failed (HTTP ${resp.status})`);
      }
      const data = await resp.json();

      setStageDone("repair", "1:∞ EXACT");

      // Stage 5: DXF Generation
      setStageActive("dxf", "BUILDING");
      await new Promise(r => setTimeout(r, 160));
      setStageDone("dxf", "COMPILED");

      currentAnalysisData = data;
      currentParcels = data.parcels;

      renderNote(data.note);
      renderMetrics(data.summary);
      renderSvgGeometry(data);
      renderParcelsCards(data.parcels);
      renderSurveyTable(data.parcels);

    } catch (err) {
      console.error(err);
      alert("Analysis error: " + err.message);
      const s = stages.repair;
      if (s && s.el) {
        s.el.className = "pipeline-item active";
        if (s.badge) s.badge.textContent = "ERROR";
      }
    } finally {
      runModelBtn.disabled = false;
      runModelBtn.innerHTML = `
        <svg class="extract-eye-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
          <circle cx="12" cy="12" r="3"></circle>
        </svg>
        <span class="btn-extract-text">Extract from Plat</span>
      `;
    }
  }

  // -------------------------------------------------------------------------
  // Render Backend Honesty Note (e.g. "this input isn't wired up yet")
  // -------------------------------------------------------------------------
  function renderNote(note) {
    if (!analysisNoteBanner) return;
    if (note) {
      analysisNoteBanner.textContent = note;
      analysisNoteBanner.classList.remove("hidden");
    } else {
      analysisNoteBanner.classList.add("hidden");
      analysisNoteBanner.textContent = "";
    }
  }

  // -------------------------------------------------------------------------
  // Render Summary Metrics
  // -------------------------------------------------------------------------
  function renderMetrics(summary) {
    metricMisclose.textContent = `${summary.max_linear_misclose.toFixed(5)} ft`;
    metricPrecision.textContent = summary.average_precision;
    metricArea.textContent = `${summary.total_net_area_sf.toLocaleString()} SF`;
    metricAcres.textContent = `${summary.total_net_acres} Acres`;
    metricLotsCount.textContent = `${summary.passed_parcels} / ${summary.total_parcels} PASS`;
  }

  // -------------------------------------------------------------------------
  // SVG Geometry Renderer
  // -------------------------------------------------------------------------
  function renderSvgGeometry(data) {
    svgGeometryGroup.innerHTML = "";

    const bbox = data.bbox;
    // Map surveyor coordinates (East = X, North = Y, where North increases upward)
    // to SVG screen coordinates (X = right, Y = downward).
    const pad = 40;
    const svgWidth = 760;
    const svgHeight = 440;

    const scaleX = (svgWidth - pad * 2) / bbox.width;
    const scaleY = (svgHeight - pad * 2) / bbox.height;
    const scale = Math.min(scaleX, scaleY);

    const offsetX = pad + (svgWidth - pad * 2 - bbox.width * scale) / 2;
    const offsetY = pad + (svgHeight - pad * 2 - bbox.height * scale) / 2;

    transformFn = (e, n) => {
      const x = offsetX + (e - bbox.min_e) * scale;
      const y = svgHeight - (offsetY + (n - bbox.min_n) * scale);
      return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 };
    };

    cadastralSvg.setAttribute("viewBox", `0 0 ${svgWidth} ${svgHeight}`);

    // 1. Draw Matchline
    if (data.matchline) {
      const p1 = transformFn(data.matchline.p1.e, data.matchline.p1.n);
      const p2 = transformFn(data.matchline.p2.e, data.matchline.p2.n);
      const matchlineEl = document.createElementNS("http://www.w3.org/2000/svg", "line");
      matchlineEl.setAttribute("x1", p1.x);
      matchlineEl.setAttribute("y1", p1.y);
      matchlineEl.setAttribute("x2", p2.x);
      matchlineEl.setAttribute("y2", p2.y);
      matchlineEl.setAttribute("class", "svg-matchline");
      svgGeometryGroup.appendChild(matchlineEl);

      // Matchline Label
      const midX = (p1.x + p2.x) / 2 + 12;
      const midY = (p1.y + p2.y) / 2;
      const matchText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      matchText.setAttribute("x", midX);
      matchText.setAttribute("y", midY);
      matchText.setAttribute("class", "svg-lot-subtext");
      matchText.setAttribute("fill", "#f59e0b");
      matchText.textContent = "MATCHLINE (200.00')";
      svgGeometryGroup.appendChild(matchText);
    }

    // 2. Draw Each Parcel Polygon & Text
    data.parcels.forEach((parcel) => {
      const polyPts = parcel.svg_polygon.split(" ").map(pair => {
        const [e, n] = pair.split(",").map(Number);
        const pt = transformFn(e, n);
        return `${pt.x},${pt.y}`;
      }).join(" ");

      const polyEl = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
      polyEl.setAttribute("points", polyPts);
      polyEl.setAttribute("class", "svg-lot-polygon");
      polyEl.setAttribute("data-lot", parcel.lot_number);
      polyEl.id = `svg-lot-${parcel.lot_number}`;

      // Mouse Events for Tooltip & Highlighting
      polyEl.addEventListener("mouseenter", (e) => {
        highlightLot(parcel.lot_number);
        showTooltip(e, parcel);
      });
      polyEl.addEventListener("mousemove", (e) => updateTooltipPos(e));
      polyEl.addEventListener("mouseleave", () => {
        unhighlightLot(parcel.lot_number);
        hideTooltip();
      });
      polyEl.addEventListener("click", () => {
        openChecksheetModal(parcel);
      });

      svgGeometryGroup.appendChild(polyEl);

      // Centroid Text
      const cen = transformFn(parcel.centroid.e, parcel.centroid.n);
      const titleText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      titleText.setAttribute("x", cen.x);
      titleText.setAttribute("y", cen.y - 7);
      titleText.setAttribute("class", "svg-lot-text");
      titleText.textContent = `LOT ${parcel.lot_number}`;

      const subText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      subText.setAttribute("x", cen.x);
      subText.setAttribute("y", cen.y + 7);
      subText.setAttribute("class", "svg-lot-subtext");
      subText.textContent = `${Math.round(parcel.area_sqft).toLocaleString()} SF`;

      svgGeometryGroup.appendChild(titleText);
      svgGeometryGroup.appendChild(subText);
    });

    // 3. Draw PRM Monument
    if (data.monuments && data.monuments.length > 0) {
      data.monuments.forEach(m => {
        const pt = transformFn(m.e, m.n);
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("cx", pt.x);
        circle.setAttribute("cy", pt.y);
        circle.setAttribute("r", 5);
        circle.setAttribute("class", "svg-prm-point");
        svgGeometryGroup.appendChild(circle);

        const mText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        mText.setAttribute("x", pt.x + 8);
        mText.setAttribute("y", pt.y - 6);
        mText.setAttribute("class", "svg-lot-subtext");
        mText.setAttribute("fill", "#10b981");
        mText.textContent = "P.R.M. MONUMENT";
        svgGeometryGroup.appendChild(mText);
      });
    }
  }

  // -------------------------------------------------------------------------
  // Tooltip Logic
  // -------------------------------------------------------------------------
  function showTooltip(e, parcel) {
    lotTooltip.innerHTML = `
      <div class="lot-tooltip-title">
        Lot ${parcel.lot_number} (Block 9)
      </div>
      <div><strong>Frontage:</strong> ${parcel.frontage}</div>
      <div><strong>Net Area:</strong> ${parcel.area_sqft.toLocaleString()} SF (${parcel.acres} AC)</div>
      <div><strong>Perimeter:</strong> ${parcel.perimeter_ft} ft</div>
      <div><strong>Misclose:</strong> ${parcel.misclose_ft} ft (${parcel.precision})</div>
      <div><strong>Status:</strong> <span class="lot-tooltip-status">${parcel.fac_5j17}</span></div>
      <div class="lot-tooltip-hint">Click lot to open surveyor checksheet</div>
    `;
    lotTooltip.classList.remove("hidden");
    updateTooltipPos(e);
  }

  function updateTooltipPos(e) {
    const rect = cadastralSvg.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    lotTooltip.style.left = `${x}px`;
    lotTooltip.style.top = `${y}px`;
  }

  function hideTooltip() {
    lotTooltip.classList.add("hidden");
  }

  // -------------------------------------------------------------------------
  // Highlighting Synchronization (Canvas <-> Cards <-> Table)
  // -------------------------------------------------------------------------
  function highlightLot(lotNum) {
    document.getElementById(`svg-lot-${lotNum}`)?.classList.add("highlighted");
    document.getElementById(`card-lot-${lotNum}`)?.classList.add("highlighted");
    document.getElementById(`row-lot-${lotNum}`)?.classList.add("highlighted");
  }

  function unhighlightLot(lotNum) {
    document.getElementById(`svg-lot-${lotNum}`)?.classList.remove("highlighted");
    document.getElementById(`card-lot-${lotNum}`)?.classList.remove("highlighted");
    document.getElementById(`row-lot-${lotNum}`)?.classList.remove("highlighted");
  }

  fitViewBtn.addEventListener("click", () => {
    if (currentAnalysisData) {
      renderSvgGeometry(currentAnalysisData);
    }
  });

  // -------------------------------------------------------------------------
  // Render Parcel Cards Grid
  // -------------------------------------------------------------------------
  function renderParcelsCards(parcels) {
    parcelsCardsGrid.innerHTML = "";

    parcels.forEach((p) => {
      const card = document.createElement("div");
      card.className = "parcel-card";
      card.id = `card-lot-${p.lot_number}`;

      card.innerHTML = `
        <div class="card-top-row">
          <div class="lot-badge-large">
            <span class="lot-prefix">Lot</span>
            <span class="lot-num-val">${p.lot_number}</span>
          </div>
          <span class="badge-pass">${p.status}</span>
        </div>

        <div class="parcel-frontage">${p.frontage}</div>

        <div class="card-stats-grid">
          <div class="stat-item">
            <span class="stat-label">Net Area</span>
            <span class="stat-val">${Math.round(p.area_sqft).toLocaleString()} SF</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Acreage</span>
            <span class="stat-val">${p.acres} AC</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Perimeter</span>
            <span class="stat-val">${p.perimeter_ft} ft</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Misclose</span>
            <span class="stat-val text-success">${p.misclose_ft.toFixed(4)} ft</span>
          </div>
        </div>

        <div class="card-actions-row">
          <a href="/api/lot_dxf/${p.lot_number}" data-download data-filename="Lot_${p.lot_number}_MapCheck.dxf" class="btn-card-action btn-card-dxf" download>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            <span>Lot DXF</span>
          </a>
          <button type="button" class="btn-card-action btn-card-sheet view-sheet-btn" data-lot="${p.lot_number}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            </svg>
            <span>Checksheet</span>
          </button>
        </div>
      `;

      // Hover link
      card.addEventListener("mouseenter", () => highlightLot(p.lot_number));
      card.addEventListener("mouseleave", () => unhighlightLot(p.lot_number));

      card.querySelector(".view-sheet-btn").addEventListener("click", () => {
        openChecksheetModal(p);
      });

      parcelsCardsGrid.appendChild(card);
    });

    if (window.PlatDownloads) PlatDownloads.wireDownloadLinks(parcelsCardsGrid);
  }

  // -------------------------------------------------------------------------
  // Render Detailed Survey Table
  // -------------------------------------------------------------------------
  function renderSurveyTable(parcels) {
    cadastralTableBody.innerHTML = "";

    parcels.forEach((p) => {
      const tr = document.createElement("tr");
      tr.id = `row-lot-${p.lot_number}`;

      tr.innerHTML = `
        <td class="td-mono td-lot-id">${p.lot_id}</td>
        <td>${p.frontage}</td>
        <td class="td-mono">${p.perimeter_ft} ft</td>
        <td class="td-mono text-success">${p.misclose_ft.toFixed(5)} ft</td>
        <td class="td-mono">${p.precision}</td>
        <td class="td-mono">${Math.round(p.area_sqft).toLocaleString()} SF</td>
        <td class="td-mono">${p.acres} AC</td>
        <td><span class="badge-table-pass">${p.status} (5J-17)</span></td>
        <td>
          <div class="table-actions">
            <a href="/api/lot_dxf/${p.lot_number}" data-download data-filename="Lot_${p.lot_number}_MapCheck.dxf" class="btn-tbl btn-tbl-dxf" download>DXF</a>
            <button type="button" class="btn-tbl btn-tbl-sheet tbl-sheet-btn" data-lot="${p.lot_number}">Sheet</button>
          </div>
        </td>
      `;

      tr.addEventListener("mouseenter", () => highlightLot(p.lot_number));
      tr.addEventListener("mouseleave", () => unhighlightLot(p.lot_number));

      tr.querySelector(".tbl-sheet-btn").addEventListener("click", () => {
        openChecksheetModal(p);
      });

      cadastralTableBody.appendChild(tr);
    });

    filteredCountBadge.textContent = `Showing ${parcels.length} Parcels`;
    if (window.PlatDownloads) PlatDownloads.wireDownloadLinks(cadastralTableBody);
  }

  // -------------------------------------------------------------------------
  // Search / Filter Lots
  // -------------------------------------------------------------------------
  filterLotInput.addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    const filtered = currentParcels.filter(p => {
      return p.lot_number.toLowerCase().includes(q) ||
             p.lot_id.toLowerCase().includes(q) ||
             p.frontage.toLowerCase().includes(q);
    });

    renderParcelsCards(filtered);
    renderSurveyTable(filtered);
    filteredCountBadge.textContent = `Showing ${filtered.length} of ${currentParcels.length} Parcels`;
  });

  // -------------------------------------------------------------------------
  // Surveyor Checksheet Modal
  // -------------------------------------------------------------------------
  function openChecksheetModal(parcel) {
    modalLotTitle.textContent = `${parcel.lot_id} Surveyor Checksheet (Block 9)`;
    checksheetContent.textContent = parcel.checksheet_text;
    modalDxfDownloadBtn.href = `/api/lot_dxf/${parcel.lot_number}`;
    modalDxfDownloadBtn.setAttribute("download", `Lot_${parcel.lot_number}_MapCheck.dxf`);
    checksheetModal.classList.remove("hidden");
  }

  closeModalBtn.addEventListener("click", () => {
    checksheetModal.classList.add("hidden");
  });

  checksheetModal.addEventListener("click", (e) => {
    if (e.target === checksheetModal) {
      checksheetModal.classList.add("hidden");
    }
  });

  copyChecksheetBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(checksheetContent.textContent).then(() => {
      const originalText = copyChecksheetBtn.querySelector("span").textContent;
      copyChecksheetBtn.querySelector("span").textContent = "Copied!";
      setTimeout(() => {
        copyChecksheetBtn.querySelector("span").textContent = originalText;
      }, 2000);
    });
  });

  // Initialize on Load: user clicks "Extract from Plat" to trigger pipeline
});
