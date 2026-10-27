// Single-patch point data cache — set on load, used for server-side recovery
// when the backend loses its patch files while labels remain in memory.
let _positions = null  // Float32Array, count*3
let _origCls   = null  // Float32Array, count
let _origin    = { x: 0, y: 0 }  // positions are x/y relative to this (world coords)

export function setPatchCache(positions, origCls, origin = { x: 0, y: 0 }) {
  _positions = positions
  _origCls   = origCls
  _origin    = origin
}

export function getPatchCache() {
  return { positions: _positions, origCls: _origCls, origin: _origin }
}

export function clearPatchCache() {
  _positions = null
  _origCls   = null
  _origin    = { x: 0, y: 0 }
}
