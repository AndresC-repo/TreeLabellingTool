// Single-patch point data cache — set on load, used for server-side recovery
// when the backend loses its patch files while labels remain in memory.
let _positions = null  // Float32Array, count*3
let _origCls   = null  // Float32Array, count

export function setPatchCache(positions, origCls) {
  _positions = positions
  _origCls   = origCls
}

export function getPatchCache() {
  return { positions: _positions, origCls: _origCls }
}

export function clearPatchCache() {
  _positions = null
  _origCls   = null
}
