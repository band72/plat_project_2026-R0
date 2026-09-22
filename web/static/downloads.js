/**
 * downloads.js -- Robust cross-origin-safe file download helper.
 *
 * Why this exists: the plain `<a href="..." download>` pattern only forces a
 * save-to-disk when the link is SAME-ORIGIN. The moment this UI runs as an
 * embedded plugin on a third-party site (see /plat-reader), every download
 * link points at a different origin (the API host) -- and browsers silently
 * IGNORE the `download` attribute for cross-origin URLs, just navigating to
 * (or opening a viewer for) the file instead of saving it. That is the bug
 * behind "downloads need to reach the user's computer."
 *
 * Fix: fetch the file as a Blob (an explicit CORS request we control) and
 * save it from a same-origin `blob:` URL, which always honors `download`
 * regardless of where the bytes came from. Where the browser supports it
 * (File System Access API, Chromium-based browsers), also offer the user an
 * explicit choice of save location via the native Save-As dialog.
 *
 * Framework-free, dependency-free, safe to drop into any page: everything is
 * namespaced under `window.PlatDownloads` so it never collides with a host
 * site's own globals.
 */
(function (global) {
  "use strict";

  /** Extract `filename=...` from a Content-Disposition response header, if present. */
  function filenameFromContentDisposition(header) {
    if (!header) return null;
    const starMatch = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header);
    if (starMatch) {
      try {
        return decodeURIComponent(starMatch[1].trim().replace(/^"|"$/g, ""));
      } catch (_e) {
        // fall through to the plain-filename match below
      }
    }
    const plainMatch = /filename="?([^";]+)"?/i.exec(header);
    return plainMatch ? plainMatch[1].trim() : null;
  }

  /**
   * Download `url` to the user's computer as `suggestedName`.
   *
   * @param {string} url            Absolute or relative URL to fetch.
   * @param {string} suggestedName  Filename to save as.
   * @param {{ preferPicker?: boolean, onStart?: Function, onDone?: Function, onError?: Function }} [opts]
   *   preferPicker: when the browser supports it, show a native "Save As"
   *   dialog so the user can choose the destination folder/filename (the
   *   "or have a choice" requirement) instead of silently using the default
   *   downloads folder.
   */
  async function downloadFile(url, suggestedName, opts) {
    opts = opts || {};
    if (typeof opts.onStart === "function") opts.onStart();

    try {
      const useSavePicker = opts.preferPicker !== false && typeof global.showSaveFilePicker === "function";

      if (useSavePicker) {
        try {
          const handle = await global.showSaveFilePicker({ suggestedName });
          const resp = await fetch(url, { credentials: "same-origin" });
          if (!resp.ok) throw new Error(`Download failed (HTTP ${resp.status})`);
          const writable = await handle.createWritable();
          await resp.body.pipeTo(writable).catch(async () => {
            // Streaming pipe unsupported in this browser -- fall back to a
            // single blob write against the same handle.
            await writable.write(await resp.blob());
            await writable.close();
          });
          if (typeof opts.onDone === "function") opts.onDone("saved");
          return "saved";
        } catch (pickerErr) {
          if (pickerErr && pickerErr.name === "AbortError") {
            // User cancelled the Save dialog -- not an error, just stop.
            if (typeof opts.onDone === "function") opts.onDone("cancelled");
            return "cancelled";
          }
          // Any other picker failure (e.g. permission, unsupported combo):
          // fall through to the plain blob-anchor download below.
        }
      }

      const resp = await fetch(url, { credentials: "same-origin" });
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
      // Give the browser a moment to start the save before revoking.
      setTimeout(() => URL.revokeObjectURL(blobUrl), 4000);
      if (typeof opts.onDone === "function") opts.onDone("saved");
      return "saved";
    } catch (err) {
      if (typeof opts.onError === "function") opts.onError(err);
      else throw err;
      return "error";
    }
  }

  /**
   * Wire up every element matching `selector` inside `root` (default: whole
   * document) so a left-click triggers a robust download instead of relying
   * on the (cross-origin-unsafe) `download` attribute. Each element must
   * carry `href` (or `data-href`) for the source URL; the filename comes
   * from `data-filename`, falling back to the `download` attribute, falling
   * back to the URL's last path segment.
   */
  function wireDownloadLinks(root, selector, opts) {
    root = root || document;
    selector = selector || "[data-download]";
    root.querySelectorAll(selector).forEach((el) => {
      if (el.__platDownloadWired) return;
      el.__platDownloadWired = true;
      el.addEventListener("click", (e) => {
        e.preventDefault();
        const url = el.getAttribute("data-href") || el.getAttribute("href");
        if (!url) return;
        const name = el.getAttribute("data-filename")
          || el.getAttribute("download")
          || url.split("/").pop()
          || "download";
        const originalHTML = el.innerHTML;
        downloadFile(url, name, Object.assign({
          onStart: () => el.classList.add("is-downloading"),
          onDone: (status) => {
            el.classList.remove("is-downloading");
            // Only flash "success" when a file was actually saved -- the
            // user cancelling the native Save dialog isn't a success.
            if (status === "saved") {
              el.classList.add("download-ok");
              setTimeout(() => el.classList.remove("download-ok"), 1500);
            }
          },
          onError: (err) => {
            el.classList.remove("is-downloading");
            console.error("Download failed:", err);
            el.classList.add("download-failed");
            setTimeout(() => el.classList.remove("download-failed"), 2000);
            el.innerHTML = originalHTML;
          },
        }, opts || {}));
      });
    });
  }

  global.PlatDownloads = { downloadFile, wireDownloadLinks };
})(window);
