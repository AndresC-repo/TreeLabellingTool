// Web Worker: project 3D points to screen-space, run PIP test
// Message in: { positions: Float32Array, mvpMatrix: Float32Array (16 elements, column-major), screenW, screenH, polygon: [{x,y}] }
// Message out: { indices: Uint32Array }

function multiplyMVP(m, x, y, z) {
  // m is column-major Float32Array[16] (THREE.js Matrix4 elements)
  const w = m[3]*x + m[7]*y + m[11]*z + m[15]
  if (Math.abs(w) < 1e-10) return null
  return {
    x: (m[0]*x + m[4]*y + m[8]*z  + m[12]) / w,
    y: (m[1]*x + m[5]*y + m[9]*z  + m[13]) / w,
  }
}

function pointInPolygon(px, py, poly) {
  let inside = false
  let j = poly.length - 1
  for (let i = 0; i < poly.length; i++) {
    const xi = poly[i].x, yi = poly[i].y
    const xj = poly[j].x, yj = poly[j].y
    if ((yi > py) !== (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi) inside = !inside
    j = i
  }
  return inside
}

self.onmessage = function(e) {
  const { positions, mvpMatrix, screenW, screenH, polygon } = e.data
  const count = positions.length / 3
  const selected = []

  for (let i = 0; i < count; i++) {
    const x = positions[i*3], y = positions[i*3+1], z = positions[i*3+2]
    const ndc = multiplyMVP(mvpMatrix, x, y, z)
    if (!ndc) continue
    // NDC [-1,1] to screen pixels [0, screenW/H]
    const sx = (ndc.x + 1) / 2 * screenW
    const sy = (1 - ndc.y) / 2 * screenH
    if (pointInPolygon(sx, sy, polygon)) selected.push(i)
  }

  self.postMessage({ indices: new Uint32Array(selected) })
}
