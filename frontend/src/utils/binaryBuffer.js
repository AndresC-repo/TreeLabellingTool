/**
 * Parse a 2D binary buffer (5 floats/point: x, y, r, g, b)
 * Returns { positions: Float32Array [x,y,...], colors: Float32Array [r,g,b,...], count }
 */
export function parse2DBuffer(arrayBuffer) {
  const data = new Float32Array(arrayBuffer)
  const count = data.length / 5
  const positions = new Float32Array(count * 2)
  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    positions[i * 2]     = data[i * 5]
    positions[i * 2 + 1] = data[i * 5 + 1]
    colors[i * 3]     = data[i * 5 + 2]
    colors[i * 3 + 1] = data[i * 5 + 3]
    colors[i * 3 + 2] = data[i * 5 + 4]
  }
  return { positions, colors, count }
}

/**
 * Parse a 3D binary buffer (8 floats/point: x, y, z, r, g, b, classification, orig_classification)
 * Returns { positions, colors, classifications, origClassifications, count }
 *   classifications     — current in-memory labels (may include custom 101+, 201+, etc.)
 *   origClassifications — original ASPRS classification from the LAS file (never overwritten)
 */
export function parse3DBuffer(arrayBuffer) {
  const data = new Float32Array(arrayBuffer)
  const count = data.length / 8
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 3)
  const classifications = new Float32Array(count)
  const origClassifications = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    positions[i * 3]     = data[i * 8]
    positions[i * 3 + 1] = data[i * 8 + 1]
    positions[i * 3 + 2] = data[i * 8 + 2]
    colors[i * 3]     = data[i * 8 + 3]
    colors[i * 3 + 1] = data[i * 8 + 4]
    colors[i * 3 + 2] = data[i * 8 + 5]
    classifications[i]     = data[i * 8 + 6]
    origClassifications[i] = data[i * 8 + 7]
  }
  return { positions, colors, classifications, origClassifications, count }
}
