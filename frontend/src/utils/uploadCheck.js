// Client-side checks before uploading, so problems show up before a long upload.
// Files are handled as items { file, folder }: folder is the path of the folder the file
// came from ("Gainesville/tiles"), or null for single files. The tool groups by it.
export const MAX_UPLOAD_BYTES = 2 * 1024 ** 3   // keep in sync with backend config.MAX_UPLOAD_BYTES

const EXT_RE = /\.(las|laz)$/i

function fmtSize(bytes) {
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${Math.round(bytes / 1024 ** 2)} MB`
}

const dirOf = path => {
  const i = (path || '').lastIndexOf('/')
  return i > 0 ? path.slice(0, i) : null
}

/** Unique key of a loaded file: folder + name (the same name may exist in two folders) */
export const fileKey = (folder, name) => `${(folder || '').toLowerCase()}/${(name || '').toLowerCase()}`

/** Files from an <input type="file"> (with or without webkitdirectory) → items */
export function itemsFromInput(fileList) {
  return Array.from(fileList).map(file => ({ file, folder: dirOf(file.webkitRelativePath) }))
}

/**
 * Files from a drop → items. Dropped folders are walked recursively (browsers only
 * give the folder itself in dataTransfer.files, not its contents).
 */
export async function itemsFromDrop(dataTransfer) {
  const entries = Array.from(dataTransfer?.items ?? [])
    .map(it => (it.kind === 'file' && it.webkitGetAsEntry) ? it.webkitGetAsEntry() : null)
  if (!entries.some(e => e?.isDirectory)) {
    return Array.from(dataTransfer.files).map(file => ({ file, folder: null }))
  }
  const out = []
  const readAll = reader => new Promise((resolve, reject) => {
    const all = []
    const next = () => reader.readEntries(batch => {     // returns at most ~100 entries per call
      if (!batch.length) resolve(all)
      else { all.push(...batch); next() }
    }, reject)
    next()
  })
  async function walk(entry, dir) {
    if (!entry) return
    if (entry.isFile) {
      const file = await new Promise((res, rej) => entry.file(res, rej))
      out.push({ file, folder: dir })
    } else if (entry.isDirectory) {
      const sub = dir ? `${dir}/${entry.name}` : entry.name
      for (const child of await readAll(entry.createReader())) await walk(child, sub)
    }
  }
  for (const e of entries) await walk(e, null)
  return out
}

/**
 * Split items into the ones to upload and human-readable reasons for the rest.
 * Non-.las files inside a folder are skipped silently (folders often hold other files).
 * @param {{file: File, folder: string|null}[]} items
 * @param {string[]} loadedKeys  fileKey(folder, name) of files already in the list
 */
export function checkFiles(items, loadedKeys = []) {
  const seen = new Set(loadedKeys)
  const accepted = []
  const skipped = []
  let ignored = 0

  for (const it of items) {
    const { file: f, folder } = it.file ? it : { file: it, folder: null }
    const key = fileKey(folder, f.name)
    const label = folder ? `${folder}/${f.name}` : f.name
    if (!EXT_RE.test(f.name)) {
      if (folder) ignored++
      else skipped.push(`${label}: not a .las/.laz file`)
    } else if (f.size > MAX_UPLOAD_BYTES) {
      skipped.push(`${label}: ${fmtSize(f.size)} exceeds the ${fmtSize(MAX_UPLOAD_BYTES)} limit`)
    } else if (seen.has(key)) {
      skipped.push(`${label}: already loaded`)
    } else {
      seen.add(key)
      accepted.push({ file: f, folder })
    }
  }
  return { accepted, skipped, ignored }
}

/** Path of an entry inside its top folder: "sub/c.las" for folder "Gainesville/sub" */
export const pathInFolder = e => {
  const rest = (e.folder || '').split('/').slice(1).join('/')
  return rest ? `${rest}/${e.filename}` : e.filename
}

/**
 * Group session entries for display: files without a folder first, then one group per
 * top-level folder (the folder that was chosen or dropped), subfolders included, so
 * deleting the group removes everything that came with it.
 */
export function groupByFolder(entries) {
  const loose = [], map = new Map()
  for (const e of entries) {
    if (!e.folder) { loose.push(e); continue }
    const top = e.folder.split('/')[0]
    if (!map.has(top)) map.set(top, [])
    map.get(top).push(e)
  }
  const cmp = (a, b) => a.localeCompare(b, undefined, { numeric: true })
  const folders = [...map.entries()]
    .sort(([a], [b]) => cmp(a, b))
    .map(([name, items]) => ({ name, items: items.sort((a, b) => cmp(pathInFolder(a), pathInFolder(b))) }))
  return { loose, folders }
}
