// Client-side checks before uploading, so problems show up before a long upload.
export const MAX_UPLOAD_BYTES = 2 * 1024 ** 3   // keep in sync with backend config.MAX_UPLOAD_BYTES

const EXT_RE = /\.(las|laz)$/i

function fmtSize(bytes) {
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${Math.round(bytes / 1024 ** 2)} MB`
}

/**
 * Split files into the ones to upload and human-readable reasons for the rest.
 * @param {File[]} files
 * @param {string[]} loadedNames  filenames already in the session list
 */
export function checkFiles(files, loadedNames = []) {
  const seen = new Set(loadedNames.map(n => n.toLowerCase()))
  const accepted = []
  const skipped = []

  for (const f of files) {
    const key = f.name.toLowerCase()
    if (!EXT_RE.test(f.name)) {
      skipped.push(`${f.name}: not a .las/.laz file`)
    } else if (f.size > MAX_UPLOAD_BYTES) {
      skipped.push(`${f.name}: ${fmtSize(f.size)} exceeds the ${fmtSize(MAX_UPLOAD_BYTES)} limit`)
    } else if (seen.has(key)) {
      skipped.push(`${f.name}: already loaded`)
    } else {
      seen.add(key)
      accepted.push(f)
    }
  }
  return { accepted, skipped }
}
