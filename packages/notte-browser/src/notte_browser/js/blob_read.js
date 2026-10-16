// Returns base64 so we can ferry bytes safely across CDP.
async (url) => {
  const blob = window.__notte_blob_capture && window.__notte_blob_capture.get(url);
  if (!blob) return null;
  const buf = await blob.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}
