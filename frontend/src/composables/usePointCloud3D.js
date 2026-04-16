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

// ASPRS classification colors — mirrors backend/services/projection.py CLASSIFICATION_COLORS
const ASPRS_COLORS = {
  0:  [0.28, 0.28, 0.32],  // GND / Never classified
  1:  [0.7,  0.7,  0.7],   // Unclassified
  2:  [0.55, 0.27, 0.07],  // Ground (brown)
  3:  [0.13, 0.55, 0.13],  // Low vegetation
  4:  [0.0,  0.8,  0.0],   // Medium vegetation
  5:  [0.0,  0.5,  0.0],   // High vegetation
  6:  [1.0,  0.0,  0.0],   // Building (red)
  7:  [1.0,  0.5,  0.0],   // Low point (noise)
  9:  [0.0,  0.5,  1.0],   // Water
  17: [0.8,  0.8,  1.0],   // Bridge deck
  18: [1.0,  0.0,  1.0],   // High noise
}

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

// Returns color for a label value, respecting showAllLabels toggle.
// - labels < 100: always use ASPRS color map
// - labels >= 100: use palette when showAllLabels=true, gray when false
function colorForLabel(labelValue, showAllLabels = true) {
  if (labelValue <= 99) {
    return ASPRS_COLORS[labelValue] ?? [0.55, 0.55, 0.55]
  }
  if (!showAllLabels) return [0.28, 0.28, 0.32]
  return paletteColor(labelValue)
}

// ── Terrain grid from class-2 (ASPRS ground) points ──────────────────────────
// Returns null when no ground points exist.
// Cells with no ground coverage are filled with the average Z of all ground points.
function _buildGroundTerrain(positions, origCls, count) {
  const GRID = 64
  const BG_COLOR = [0.1, 0.1, 0.18]

  // Collect bounding box over all points
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
  for (let i = 0; i < count; i++) {
    const x = positions[i*3], y = positions[i*3+1]
    if (x < xMin) xMin = x; if (x > xMax) xMax = x
    if (y < yMin) yMin = y; if (y > yMax) yMax = y
  }
  const xRange = Math.max(xMax - xMin, 1e-6)
  const yRange = Math.max(yMax - yMin, 1e-6)

  // Min Z per cell from ASPRS class-2 points; also track avg ground Z for fallback
  const terrain = new Float32Array(GRID * GRID).fill(Infinity)
  const hasCover = new Uint8Array(GRID * GRID)
  let groundSum = 0, groundCount = 0

  for (let i = 0; i < count; i++) {
    if (Math.round(origCls[i]) !== 2) continue
    const gz = positions[i*3+2]
    groundSum += gz
    groundCount++
    const cx = Math.min(((positions[i*3]   - xMin) / xRange * GRID) | 0, GRID - 1)
    const cy = Math.min(((positions[i*3+1] - yMin) / yRange * GRID) | 0, GRID - 1)
    const idx = cy * GRID + cx
    if (gz < terrain[idx]) terrain[idx] = gz
    hasCover[idx] = 1
  }

  if (groundCount === 0) return null

  const avgGroundZ = groundSum / groundCount
  for (let i = 0; i < GRID * GRID; i++) {
    if (!hasCover[i]) terrain[i] = avgGroundZ
  }

  return { terrain, GRID, xMin, yMin, xRange, yRange, BG_COLOR }
}

// ── DTM color computation ─────────────────────────────────────────────────────
// Shows only ASPRS class-2 (ground) points, colored by elevation.
// Non-ground points get background color.
// Returns null when no ground points exist.
function computeDTMColors(positions, origCls, count) {
  const grid = _buildGroundTerrain(positions, origCls, count)
  if (!grid) return null

  const { terrain, GRID, xMin, yMin, xRange, yRange, BG_COLOR } = grid

  // Z range from ground points only
  let zMin = Infinity, zMax = -Infinity
  for (let i = 0; i < count; i++) {
    if (Math.round(origCls[i]) !== 2) continue
    const z = positions[i*3+2]
    if (z < zMin) zMin = z
    if (z > zMax) zMax = z
  }
  const zRange = Math.max(zMax - zMin, 1e-6)

  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    if (Math.round(origCls[i]) !== 2) {
      // Non-ground → background (hidden)
      colors[i*3] = BG_COLOR[0]; colors[i*3+1] = BG_COLOR[1]; colors[i*3+2] = BG_COLOR[2]
      continue
    }
    const t = (positions[i*3+2] - zMin) / zRange
    // Blue (low) → green → red (high)
    colors[i*3]   = t < 0.5 ? 0              : (t - 0.5) * 2
    colors[i*3+1] = t < 0.5 ? t * 2          : 1 - (t - 0.5) * 2
    colors[i*3+2] = t < 0.5 ? 1 - t * 2      : 0
  }
  return colors
}

// ── CHM color computation ─────────────────────────────────────────────────────
// Shows non-ground points colored by height above terrain (Z − terrain[cell]).
// Ground points (class 2) get background color.
// Returns null when no ground points exist.
function computeCHMColors(positions, origCls, count) {
  const grid = _buildGroundTerrain(positions, origCls, count)
  if (!grid) return null

  const { terrain, GRID, xMin, yMin, xRange, yRange, BG_COLOR } = grid

  // Height above terrain for non-ground points
  let maxH = 0
  const heights = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    if (Math.round(origCls[i]) === 2) continue
    const cx = Math.min(((positions[i*3]   - xMin) / xRange * GRID) | 0, GRID - 1)
    const cy = Math.min(((positions[i*3+1] - yMin) / yRange * GRID) | 0, GRID - 1)
    const h  = Math.max(positions[i*3+2] - terrain[cy * GRID + cx], 0)
    heights[i] = h
    if (h > maxH) maxH = h
  }
  if (maxH < 1e-6) maxH = 1

  // Color: dark blue (at ground) → green → yellow (max height)
  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    if (Math.round(origCls[i]) === 2) {
      // Ground → background (hidden)
      colors[i*3] = BG_COLOR[0]; colors[i*3+1] = BG_COLOR[1]; colors[i*3+2] = BG_COLOR[2]
      continue
    }
    const t = heights[i] / maxH
    // Blue (ground level) → green → yellow (tallest)
    colors[i*3]   = t < 0.5 ? 0          : (t - 0.5) * 2
    colors[i*3+1] = t < 0.5 ? t * 2      : 1
    colors[i*3+2] = t < 0.5 ? 1 - t * 2  : 0
  }
  return colors
}

// ── Inference CHM — tree points only ─────────────────────────────────────────
// Same terrain model as computeCHMColors, but only points with inferenceLabel === 101
// are colored. Everything else (non-tree, ground) is shown as background.
// Returns null when no ground points exist (same condition as regular CHM).
function computeInferenceCHMColors(positions, origCls, inferenceLabels, count) {
  const grid = _buildGroundTerrain(positions, origCls, count)
  if (!grid) return null

  const { terrain, GRID, xMin, yMin, xRange, yRange, BG_COLOR } = grid

  let maxH = 0
  const heights = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    if (inferenceLabels[i] !== 101) continue
    const cx = Math.min(((positions[i*3]   - xMin) / xRange * GRID) | 0, GRID - 1)
    const cy = Math.min(((positions[i*3+1] - yMin) / yRange * GRID) | 0, GRID - 1)
    const h  = Math.max(positions[i*3+2] - terrain[cy * GRID + cx], 0)
    heights[i] = h
    if (h > maxH) maxH = h
  }
  if (maxH < 1e-6) maxH = 1

  const colors = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    if (inferenceLabels[i] !== 101) {
      colors[i*3] = BG_COLOR[0]; colors[i*3+1] = BG_COLOR[1]; colors[i*3+2] = BG_COLOR[2]
      continue
    }
    const t = heights[i] / maxH
    colors[i*3]   = t < 0.5 ? 0          : (t - 0.5) * 2
    colors[i*3+1] = t < 0.5 ? t * 2      : 1
    colors[i*3+2] = t < 0.5 ? 1 - t * 2  : 0
  }
  return colors
}

// ── Main composable ───────────────────────────────────────────────────────────

export function usePointCloud3D(scene, sessionId, patchId) {
  const loading = ref(false)
  const pointCount = ref(0)
  const dtmAvailable = ref(true)  // false when no class-2 ground points exist
  let pointsMesh = null
  let elevationColors = null      // original server colors (elevation), never modified
  let classificationColors = null // per-point label colors (rebuilt from currentLabels)
  let dtmColors = null            // min-Z in local cell, elevation gradient
  let chmColors = null            // height above ground, green gradient
  let filteredElevationColors = null  // elevation colors with Z filter applied
  let predictionColors = null         // per-point NN predicted class colors
  let cachedPositions = null
  let cachedClassifications = null
  let currentLabels = null        // Int32Array tracking the current label per point
  let origAsprsClassifications = null // original ASPRS classification from LAS (never changes)
  let cachedTerrainGrid = null    // result of _buildGroundTerrain — null when no class-2 points
  let inferenceCHMColors = null   // CHM colored only for tree-labeled (101) points
  let _zMin = 0, _zMax = 0       // Z bounds for filter
  let _filterLo = -Infinity, _filterHi = Infinity  // current filter bounds
  const viewMode = ref('elevation')

  async function load() {
    loading.value = true
    try {
      const res = await getPatchPoints(sessionId, patchId)
      const { positions, colors, classifications, origClassifications, count } = parse3DBuffer(res.data)
      pointCount.value = count
      elevationColors = colors.slice()

      // Classification colors — initialize from actual label values (showAllLabels=true by default)
      currentLabels = new Int32Array(count)
      classificationColors = new Float32Array(count * 3)
      for (let i = 0; i < count; i++) {
        const lv = Math.round(classifications[i])
        currentLabels[i] = lv
        const [r, g, b] = colorForLabel(lv, true)
        classificationColors[i*3] = r; classificationColors[i*3+1] = g; classificationColors[i*3+2] = b
      }

      // DTM and CHM computed from positions + original ASPRS classifications (class 2 = ground)
      cachedTerrainGrid = _buildGroundTerrain(positions, origClassifications, count)
      dtmAvailable.value = cachedTerrainGrid !== null
      dtmColors = cachedTerrainGrid ? computeDTMColors(positions, origClassifications, count) : null
      chmColors = cachedTerrainGrid ? computeCHMColors(positions, origClassifications, count) : null

      cachedPositions = positions
      cachedClassifications = classifications
      origAsprsClassifications = origClassifications

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
    if (viewMode.value === 'dtm')            return dtmColors ?? classificationColors
    if (viewMode.value === 'chm')            return chmColors ?? classificationColors
    if (viewMode.value === 'prediction')     return predictionColors ?? classificationColors
    if (viewMode.value === 'inference-chm')  return inferenceCHMColors ?? chmColors ?? classificationColors
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
    const inferenceArr = new Int32Array(count)
    for (let i = 0; i < Math.min(labels.length, count); i++) {
      const [r, g, b] = paletteColor(labels[i])
      predictionColors[i*3] = r; predictionColors[i*3+1] = g; predictionColors[i*3+2] = b
      inferenceArr[i] = labels[i]
    }
    // Compute tree-only CHM using the inference labels (101 = tree)
    if (cachedPositions && origAsprsClassifications) {
      inferenceCHMColors = computeInferenceCHMColors(
        cachedPositions, origAsprsClassifications, inferenceArr, count
      )
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

  function applyLabelColor(indices, labelValue, protectClasses = false) {
    const [r, g, b] = paletteColor(labelValue)
    for (const i of indices) {
      // Mirror backend protect-classes logic: skip ASPRS class 2 (ground) and 6 (building).
      // Use origAsprsClassifications (true ASPRS from LAS file) so protect logic works even
      // after custom labels have been applied on top.
      if (protectClasses && origAsprsClassifications) {
        const origCls = Math.round(origAsprsClassifications[i])
        if (origCls === 2 || origCls === 6) continue
      }
      if (currentLabels) currentLabels[i] = labelValue
      classificationColors[i*3] = r; classificationColors[i*3+1] = g; classificationColors[i*3+2] = b
    }
    viewMode.value = 'classification'
    _applyToMesh(classificationColors)
  }

  // Rebuild classification colors from current label state, respecting showAllLabels toggle.
  // showAllLabels=true:  color all currentLabels with full palette (101+=custom colors).
  // showAllLabels=false: only color currentLabels that are <100; anything >=100 turns gray.
  function rebuildClassificationColors(showAllLabels = true) {
    if (!currentLabels || !classificationColors) return
    const count = pointCount.value
    for (let i = 0; i < count; i++) {
      const lv = currentLabels[i]
      let r, g, b
      if (showAllLabels) {
        ;[r, g, b] = colorForLabel(lv, true)
      } else {
        // OFF: gray out labels <100 (ASPRS/original), keep >=100 in their palette colors
        if (lv < 100) {
          r = 0.28; g = 0.28; b = 0.32
        } else {
          ;[r, g, b] = paletteColor(lv)
        }
      }
      classificationColors[i*3] = r; classificationColors[i*3+1] = g; classificationColors[i*3+2] = b
    }
    if (viewMode.value === 'classification') _applyToMesh(classificationColors)
  }

  function resetColors() {
    _applyToMesh(_activeColors())
  }

  function getPositions() { return cachedPositions }

  // Returns DTM grid data for use in segmentation (passes terrain to backend).
  // Returns null when no class-2 ground points exist.
  function getDTMGrid() {
    if (!cachedTerrainGrid) return null
    const { terrain, GRID, xMin, yMin, xRange, yRange } = cachedTerrainGrid
    return {
      grid:   Array.from(terrain),   // flat float array, GRID*GRID values
      rows:   GRID,
      cols:   GRID,
      xMin,
      yMin,
      xRange,
      yRange,
    }
  }

  function dispose() {
    if (pointsMesh) {
      scene.value.remove(pointsMesh)
      pointsMesh.geometry.dispose()
      pointsMesh.material.dispose()
      pointsMesh = null
    }
  }

  function getZBounds() { return { zMin: _zMin, zMax: _zMax } }

  return { load, loading, pointCount, dtmAvailable, getDTMGrid, highlightIndices, applyLabelColor, applyPredictionColors, rebuildClassificationColors, resetColors, setViewMode, viewMode, getPositions, getZBounds, setElevationFilter, dispose }
}
