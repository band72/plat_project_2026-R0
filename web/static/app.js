/**
 * Cadastral Plat AI & COGO Engine -- Client Application Controller
 * Handles drag & drop uploads, model invocation, SVG geometry rendering,
 * parcel card & table generation, and deliverable downloads.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const dropzone = document.getElementById("platDropzone");
  const fileInput = document.getElementById("platFileInput");
  const browseFileBtn = document.getElementById("browseFileBtn");
  const uploadStatus = document.getElementById("fileUploadStatus");
  const uploadedFileNameEl = document.getElementById("uploadedFileName");
  const uploadedFileSizeEl = document.getElementById("uploadedFileSize");
  const presetSelect = document.getElementById("platPresetSelect");
  const radiusInput = document.getElementById("paramRadius");
  const piRuleInput = document.getElementById("paramPiRule");
  const runModelBtn = document.getElementById("runModelBtn");
  const modelStatusBadge = document.getElementById("modelStatusBadge");
  const pipelineSteps = [
    document.getElementById("step1"),
    document.getElementById("step2"),
    document.getElementById("step3"),
    document.getElementById("step4")
  ];

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
  let transformFn = null;

  // -------------------------------------------------------------------------
  // File Upload & Drag & Drop Handling
  // -------------------------------------------------------------------------
  browseFileBtn.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("click", (e) => {
    if (e.target !== browseFileBtn) fileInput.click();
  });

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
      handleFileUpload(fileInput.files[0]);
    }
  });

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
      presetSelect.value = "custom";
      modelStatusBadge.textContent = "Plat Uploaded";
      modelStatusBadge.className = "badge-status-pill";
    } catch (err) {
      console.error(err);
      uploadedFileNameEl.textContent = "Upload failed: " + err.message;
      uploadedFileSizeEl.textContent = "";
    }
  }

  // -------------------------------------------------------------------------
  // Model Dispatch & Execution
  // -------------------------------------------------------------------------
  runModelBtn.addEventListener("click", () => executeCadastralModel());

  async function executeCadastralModel() {
    runModelBtn.disabled = true;
    runModelBtn.innerHTML = `
      <svg class="btn-icon spinning" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M12 2a10 10 0 0 1 10 10"></path>
      </svg>
      <span>Inference Running...</span>
    `;
    modelStatusBadge.textContent = "Processing COGO...";

    // Visual Stepper Animation
    for (let i = 0; i < pipelineSteps.length; i++) {
      pipelineSteps[i].classList.remove("active");
    }

    const animateStep = (idx) => {
      if (idx < pipelineSteps.length) {
        pipelineSteps[idx].classList.add("active");
      }
    };

    animateStep(0);
    await new Promise(r => setTimeout(r, 180));
    animateStep(1);

    const formData = new FormData();
    formData.append("preset", presetSelect.value);
    if (activeUploadedFile) {
      formData.append("uploaded_filename", activeUploadedFile);
    }
    formData.append("return_radius", radiusInput.value || "25.0");
    formData.append("pi_rule_enabled", piRuleInput.checked ? "true" : "false");
    formData.append("fac_standard", "5J-17");

    try {
      const resp = await fetch("/api/analyze", {
        method: "POST",
        body: formData
      });

      if (!resp.ok) throw new Error("Model analysis failed");
      const data = await resp.json();

      animateStep(2);
      await new Promise(r => setTimeout(r, 150));
      animateStep(3);

      currentAnalysisData = data;
      currentParcels = data.parcels;

      renderMetrics(data.summary);
      renderSvgGeometry(data);
      renderParcelsCards(data.parcels);
      renderSurveyTable(data.parcels);

      modelStatusBadge.textContent = "Model Verified (PASS)";
      modelStatusBadge.style.color = "var(--accent-emerald)";
      modelStatusBadge.style.borderColor = "rgba(16, 185, 129, 0.4)";
    } catch (err) {
      console.error(err);
      alert("Analysis error: " + err.message);
      modelStatusBadge.textContent = "Execution Error";
    } finally {
      runModelBtn.disabled = false;
      runModelBtn.innerHTML = `
        <span class="btn-glow"></span>
        <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
        </svg>
        <span class="btn-label">Re-Send to Cadastral Model</span>
      `;
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
      <div style="font-weight:700; color:var(--accent-cyan); font-size:0.9rem; margin-bottom:4px;">
        Lot ${parcel.lot_number} (Block 9)
      </div>
      <div><strong>Frontage:</strong> ${parcel.frontage}</div>
      <div><strong>Net Area:</strong> ${parcel.area_sqft.toLocaleString()} SF (${parcel.acres} AC)</div>
      <div><strong>Perimeter:</strong> ${parcel.perimeter_ft} ft</div>
      <div><strong>Misclose:</strong> ${parcel.misclose_ft} ft (${parcel.precision})</div>
      <div><strong>Status:</strong> <span style="color:#34d399; font-weight:700;">${parcel.fac_5j17}</span></div>
      <div style="font-size:0.7rem; color:#94a3b8; margin-top:4px;">Click lot to open surveyor checksheet</div>
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
    const svgEl = document.getElementById(`svg-lot-${lotNum}`);
    if (svgEl) svgEl.classList.add("highlighted");

    const cardEl = document.getElementById(`card-lot-${lotNum}`);
    if (cardEl) {
      cardEl.style.borderColor = "var(--accent-cyan)";
      cardEl.style.boxShadow = "0 0 20px rgba(0, 240, 255, 0.4)";
    }

    const rowEl = document.getElementById(`row-lot-${lotNum}`);
    if (rowEl) rowEl.style.backgroundColor = "rgba(0, 240, 255, 0.08)";
  }

  function unhighlightLot(lotNum) {
    const svgEl = document.getElementById(`svg-lot-${lotNum}`);
    if (svgEl) svgEl.classList.remove("highlighted");

    const cardEl = document.getElementById(`card-lot-${lotNum}`);
    if (cardEl) {
      cardEl.style.borderColor = "";
      cardEl.style.boxShadow = "";
    }

    const rowEl = document.getElementById(`row-lot-${lotNum}`);
    if (rowEl) rowEl.style.backgroundColor = "";
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
            <span class="stat-val" style="color:#34d399;">${p.misclose_ft.toFixed(4)} ft</span>
          </div>
        </div>

        <div class="card-actions-row">
          <a href="/api/lot_dxf/${p.lot_number}" class="btn-card-action btn-card-dxf" download>
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
        <td class="td-mono" style="font-weight:700; color:var(--accent-cyan);">${p.lot_id}</td>
        <td>${p.frontage}</td>
        <td class="td-mono">${p.perimeter_ft} ft</td>
        <td class="td-mono" style="color:#34d399;">${p.misclose_ft.toFixed(5)} ft</td>
        <td class="td-mono">${p.precision}</td>
        <td class="td-mono">${Math.round(p.area_sqft).toLocaleString()} SF</td>
        <td class="td-mono">${p.acres} AC</td>
        <td><span class="badge-table-pass">${p.status} (5J-17)</span></td>
        <td>
          <div class="table-actions">
            <a href="/api/lot_dxf/${p.lot_number}" class="btn-tbl btn-tbl-dxf" download>DXF</a>
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

  // -------------------------------------------------------------------------
  // Initialize on Load (Immediate Display of Model Data)
  // -------------------------------------------------------------------------
  executeCadastralModel();
});
