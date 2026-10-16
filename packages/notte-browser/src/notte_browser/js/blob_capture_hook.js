// Installed once per download action. Wraps URL.createObjectURL so we retain a
// strong JS reference to each Blob under its URL key, which lets us read the
// bytes even after the page's URL.revokeObjectURL runs (file-saver.js pattern).
// Revocation only removes the URL->Blob mapping in the browser's registry;
// our Map keeps the Blob object alive.
//
// Both snippets must run in the page's main world, where the Blob is created.
// Chromium's top frame uses CDP; iframe and Firefox evaluation explicitly uses
// the owning frame's page world rather than Patchright's default isolated world.
(() => {
  if (window.__notte_blob_capture) return;
  const origCreate = URL.createObjectURL;
  const blobs = new Map();
  const createObjectURL = function (obj) {
    const url = origCreate.call(URL, obj);
    try { blobs.set(url, obj); } catch (e) {}
    return url;
  };
  URL.createObjectURL = createObjectURL;
  window.__notte_blob_capture = {
    get: (url) => blobs.get(url) || null,
    clear: () => blobs.clear(),
    dispose: () => {
      blobs.clear();
      if (URL.createObjectURL === createObjectURL) URL.createObjectURL = origCreate;
      delete window.__notte_blob_capture;
    },
  };
})();
