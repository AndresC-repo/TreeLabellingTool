import * as THREE from 'three'
import { getPatchPoints } from '../api/client.js'
import { parse3DBuffer } from '../utils/binaryBuffer.js'
import { ref } from 'vue'

// Label color palette: 101→Magenta, 102→Cyan, 103→Yellow, 104+→cycle
const LABEL_PALETTE = [
  [1, 0, 1],      // magenta
  [0, 1, 1],      // cyan
  [1, 1, 0],      // yellow
  [1, 0.5, 0],    // orange
  [0.5, 0, 1],    // purple
  [0, 1, 0.5],    // spring green
  [1, 0, 0.5],    // hot pink
  [0.5, 1, 0],    // chartreuse
]

function hue2rgb(p, q, t) {
  if (t < 0) t += 1; if (t > 1) t -= 1
  if (t < 1/6) return p + (q - p) * 6 * t
  if (t < 1/2) return q
  if (t < 2/3) return p + (q - p) * (2/3 - t) * 6
  return p
}
function hslToRgb(h, s, l) {
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  return [hue2rgb(p, q, h + 1/3), hue2rgb(p, q, h), hue2rgb(p, q, h - 1/3)]
}

function paletteColor(labelValue) {
  if (labelValue === 0) return [0.28, 0.28, 0.32]          // gray (GND)
  if (labelValue >= 101 && labelValue <= 108) return LABEL_PALETTE[labelValue - 101]
  // Golden-angle hash for 109+ and large instance labels (1001, 1201, …)
  const hue = ((labelValue * 137.508) % 360) / 360
  return hslToRgb(hue, 0.85, 0.55)
}

// ── DTM color computation ─────────────────────────────────────────────────────
// Only ground-classified (class 2) points are shown, colored by their own Z.
// All other points are hidden (painted background color).
function computeDTMColors(positions, classifications, count) {
  // Collect ground point Z values for normalization
  let zMin = Infinity, zMax = -Infinity
  for (let i = 0; i < count; i++) {
    if (Math.round(classifications[i]) !== 2) continue
    const z = positions[i*3+2]
    if (z < zMin) zMin = z
    if (z > zMax) zMax = z
  }
  const zRange = Math.max(zMax - zMin, 1e-6)

  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    if (Math.round(classifications[i]) !== 2) {
      // Hide non-ground points — match scene background
      colors[i*3] = 0.1; colors[i*3+1] = 0.1; colors[i*3+2] = 0.18
      continue
    }
    const t = (positions[i*3+2] - zMin) / zRange
    colors[i*3]   = t < 1/3 ? 0          : t < 2/3 ? (t - 1/3) * 3 : 1
    colors[i*3+1] = t < 1/3 ? t * 3      : t < 2/3 ? 1             : 1 - (t - 2/3) * 3
    colors[i*3+2] = t < 1/3 ? 1 - t * 3 : 0
  }
  return colors
}

// ── CHM color computation ─────────────────────────────────────────────────────
// Each point is colored by (Z − ground Z at its XY location).
// Ground = classification 2. Falls back to global min Z if no ground exists.
function computeCHMColors(positions, classifications, count) {
  const GRID   = 64
  const COARSE = 16
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
  for (let i = 0; i < count; i++) {
    const x = positions[i*3], y = positions[i*3+1]
    if (x < xMin) xMin = x; if (x > xMax) xMax = x
    if (y < yMin) yMin = y; if (y > yMax) yMax = y
  }
  const xRange = Math.max(xMax - xMin, 1e-6)
  const yRange = Math.max(yMax - yMin, 1e-6)

  // Fine DTM: min ground Z per cell
  const minGnd = new Float32Array(GRID * GRID).fill(Infinity)
  let globalGnd = Infinity
  for (let i = 0; i < count; i++) {
    if (Math.round(classifications[i]) !== 2) continue
    const z = positions[i*3+2]
    if (z < globalGnd) globalGnd = z
    const gx = Math.min((((positions[i*3]   - xMin) / xRange) * GRID) | 0, GRID - 1)
    const gy = Math.min((((positions[i*3+1] - yMin) / yRange) * GRID) | 0, GRID - 1)
    const idx = gy * GRID + gx
    if (z < minGnd[idx]) minGnd[idx] = z
  }
  if (globalGnd === Infinity) globalGnd = 0  // no ground points at all

  // Coarse DTM for gap-filling
  const coarseGnd = new Float32Array(COARSE * COARSE).fill(Infinity)
  for (let i = 0; i < count; i++) {
    if (Math.round(classifications[i]) !== 2) continue
    const z  = positions[i*3+2]
    const cx = Math.min((((positions[i*3]   - xMin) / xRange) * COARSE) | 0, COARSE - 1)
    const cy = Math.min((((positions[i*3+1] - yMin) / yRange) * COARSE) | 0, COARSE - 1)
    const idx = cy * COARSE + cx
    if (z < coarseGnd[idx]) coarseGnd[idx] = z
  }
  for (let i = 0; i < COARSE * COARSE; i++) {
    if (coarseGnd[i] === Infinity) coarseGnd[i] = globalGnd
  }

  // Merged ground grid: fine where available, coarse fallback elsewhere
  const groundZ = new Float32Array(GRID * GRID)
  for (let gy = 0; gy < GRID; gy++) {
    for (let gx = 0; gx < GRID; gx++) {
      const fine = minGnd[gy * GRID + gx]
      if (fine !== Infinity) {
        groundZ[gy * GRID + gx] = fine
      } else {
        const cy = Math.min((gy / GRID * COARSE) | 0, COARSE - 1)
        const cx = Math.min((gx / GRID * COARSE) | 0, COARSE - 1)
        groundZ[gy * GRID + gx] = coarseGnd[cy * COARSE + cx]
      }
    }
  }

  // Height above ground per point
  const heights = new Float32Array(count)
  let maxH = 0
  for (let i = 0; i < count; i++) {
    const gx = Math.min((((positions[i*3]   - xMin) / xRange) * GRID) | 0, GRID - 1)
    const gy = Math.min((((positions[i*3+1] - yMin) / yRange) * GRID) | 0, GRID - 1)
    const h  = Math.max(positions[i*3+2] - groundZ[gy * GRID + gx], 0)
    heights[i] = h
    if (h > maxH) maxH = h
  }
  if (maxH < 1e-6) maxH = 1

  // Color: dark green at 0 → bright yellow-green at max height
  // Ground points (class 2) are hidden by painting them with the background color.
  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    if (Math.round(classifications[i]) === 2) {
      // Hide ground points — match scene background
      colors[i*3] = 0.1; colors[i*3+1] = 0.1; colors[i*3+2] = 0.18
      continue
    }
    const t = heights[i] / maxH
    colors[i*3]   = t * 0.75           // R: 0 → 0.75
    colors[i*3+1] = 0.25 + t * 0.75   // G: 0.25 → 1.0
    colors[i*3+2] = 0                  // B: always 0
  }
  return colors
}

// ── Main composable ───────────────────────────────────────────────────────────

export function usePointCloud3D(scene, sessionId, patchId) {
  const loading = ref(false)
  const pointCount = ref(0)
  let pointsMesh = null
  let elevationColors = null      // original server colors (elevation), never modified
  let classificationColors = null // per-point label colors (gray default → palette on label)
  let dtmColors = null            // min-Z in local cell, elevation gradient
  let chmColors = null            // height above ground, green gradient
  let filteredElevationColors = null  // elevation colors with Z filter applied
  let predictionColors = null         // per-point NN predicted class colors
  let cachedPositions = null
  let cachedClassifications = null
  let _zMin = 0, _zMax = 0       // Z bounds for filter
  let _filterLo = -Infinity, _filterHi = Infinity  // current filter bounds
  const viewMode = ref('elevation')

  async function load() {
    loading.value = true
    try {
      const res = await getPatchPoints(sessionId, patchId)
      const { positions, colors, classifications, count } = parse3DBuffer(res.data)
      pointCount.value = count
      elevationColors = colors.slice()

      // Classification colors start as dark gray (unlabeled)
      classificationColors = new Float32Array(count * 3)
      for (let i = 0; i < count * 3; i += 3) {
        classificationColors[i] = 0.28; classificationColors[i+1] = 0.28; classificationColors[i+2] = 0.32
      }

      // DTM and CHM computed from positions + classifications
      dtmColors = computeDTMColors(positions, classifications, count)
      chmColors = computeCHMColors(positions, classifications, count)

      cachedPositions = positions
      cachedClassifications = classifications

      // Compute Z bounds from all points
      _zMin = Infinity; _zMax = -Infinity
      for (let i = 0; i < count; i++) {
        const z = positions[i*3+2]
        if (z < _zMin) _zMin = z
        if (z > _zMax) _zMax = z
      }
      _filterLo = _zMin; _filterHi = _zMax
      filteredElevationColors = null  // no filter yet
      predictionColors = null         // cleared on new load

      if (pointsMesh) { scene.value.remove(pointsMesh); pointsMesh.geometry.dispose(); pointsMesh.material.dispose() }

      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      geo.setAttribute('color', new THREE.BufferAttribute(colors.slice(), 3))
      const mat = new THREE.PointsMaterial({ size: 2, vertexColors: true, sizeAttenuation: false })
      pointsMesh = new THREE.Points(geo, mat)
      scene.value.add(pointsMesh)

      geo.computeBoundingBox()
      const center = new THREE.Vector3()
      geo.boundingBox.getCenter(center)

      // Collect ground point indices (class 2) for Label GND+ feature
      const groundIndices = []
      for (let i = 0; i < count; i++) {
        if (Math.round(classifications[i]) === 2) groundIndices.push(i)
      }

      return { center, positions, zMin: _zMin, zMax: _zMax, groundIndices }
    } finally { loading.value = false }
  }

  function _activeColors() {
    if (viewMode.value === 'classification') return classificationColors
    if (viewMode.value === 'dtm')            return dtmColors
    if (viewMode.value === 'chm')            return chmColors
    if (viewMode.value === 'prediction')     return predictionColors ?? classificationColors
    // elevation mode — return filtered version if a filter is active
    return filteredElevationColors ?? elevationColors
  }

  function setElevationFilter(zLo, zHi) {
    if (!elevationColors || !cachedPositions) return
    _filterLo = zLo; _filterHi = zHi
    const count = pointCount.value
    const BG = [0.1, 0.1, 0.18]
    if (zLo <= _zMin && zHi >= _zMax) {
      // No filtering needed — reset to original
      filteredElevationColors = null
    } else {
      filteredElevationColors = elevationColors.slice()
      for (let i = 0; i < count; i++) {
        const z = cachedPositions[i*3+2]
        if (z < zLo || z > zHi) {
          filteredElevationColors[i*3] = BG[0]
          filteredElevationColors[i*3+1] = BG[1]
          filteredElevationColors[i*3+2] = BG[2]
        }
      }
    }
    if (viewMode.value === 'elevation') _applyToMesh(_activeColors())
  }

  function applyPredictionColors(labels) {
    const count = pointCount.value
    predictionColors = new Float32Array(count * 3)
    for (let i = 0; i < Math.min(labels.length, count); i++) {
      const [r, g, b] = paletteColor(labels[i])
      predictionColors[i*3] = r; predictionColors[i*3+1] = g; predictionColors[i*3+2] = b
    }
    viewMode.value = 'prediction'
    _applyToMesh(predictionColors)
  }

  function _applyToMesh(src) {
    if (!pointsMesh) return
    const attr = pointsMesh.geometry.getAttribute('color')
    attr.array.set(src)
    attr.needsUpdate = true
  }

  function setViewMode(mode) {
    viewMode.value = mode
    _applyToMesh(_activeColors())
  }

  function highlightIndices(indices) {
    if (!pointsMesh) return
    const attr = pointsMesh.geometry.getAttribute('color')
    attr.array.set(_activeColors())
    for (const i of indices) {
      attr.array[i*3] = 1; attr.array[i*3+1] = 1; attr.array[i*3+2] = 1
    }
    attr.needsUpdate = true
  }

  function applyLabelColor(indices, labelValue) {
    const [r, g, b] = paletteColor(labelValue)
    for (const i of indices) {
      classificationColors[i*3] = r; classificationColors[i*3+1] = g; classificationColors[i*3+2] = b
    }
    viewMode.value = 'classification'
    _applyToMesh(classificationColors)
  }

  function resetColors() {
    _applyToMesh(_activeColors())
  }

  function getPositions() { return cachedPositions }

  function dispose() {
    if (pointsMesh) {
      scene.value.remove(pointsMesh)
      pointsMesh.geometry.dispose()
      pointsMesh.material.dispose()
      pointsMesh = null
    }
  }

  function getZBounds() { return { zMin: _zMin, zMax: _zMax } }

  return { load, loading, pointCount, highlightIndices, applyLabelColor, applyPredictionColors, resetColors, setViewMode, viewMode, getPositions, getZBounds, setElevationFilter, dispose }
}
