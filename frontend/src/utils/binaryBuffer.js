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
 * Parse a 3D binary buffer (7 floats/point: x, y, z, r, g, b, classification)
 * Returns { positions, colors, classifications, count }
 */
export function parse3DBuffer(arrayBuffer) {
  const data = new Float32Array(arrayBuffer)
  const count = data.length / 7
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 3)
  const classifications = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    positions[i * 3]     = data[i * 7]
    positions[i * 3 + 1] = data[i * 7 + 1]
    positions[i * 3 + 2] = data[i * 7 + 2]
    colors[i * 3]     = data[i * 7 + 3]
    colors[i * 3 + 1] = data[i * 7 + 4]
    colors[i * 3 + 2] = data[i * 7 + 5]
    classifications[i] = data[i * 7 + 6]
  }
  return { positions, colors, classifications, count }
}
