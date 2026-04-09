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

function paletteColor(labelValue) {
  const idx = Math.max(0, labelValue - 101) % LABEL_PALETTE.length
  return LABEL_PALETTE[idx]
}

export function usePointCloud3D(scene, sessionId, patchId) {
  const loading = ref(false)
  const pointCount = ref(0)
  let pointsMesh = null
  let elevationColors = null      // original server colors (elevation), never modified
  let classificationColors = null // per-point label colors (gray default → palette on label)
  let cachedPositions = null
  const viewMode = ref('elevation')

  async function load() {
    loading.value = true
    try {
      const res = await getPatchPoints(sessionId, patchId)
      const { positions, colors, count } = parse3DBuffer(res.data)
      pointCount.value = count
      elevationColors = colors.slice()

      // Classification colors start as dark gray (unlabeled)
      classificationColors = new Float32Array(count * 3)
      for (let i = 0; i < count * 3; i += 3) {
        classificationColors[i] = 0.28; classificationColors[i+1] = 0.28; classificationColors[i+2] = 0.32
      }
      cachedPositions = positions

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
      return { center, positions }
    } finally { loading.value = false }
  }

  function _activeColors() {
    return viewMode.value === 'classification' ? classificationColors : elevationColors
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
    // Start from current view
    attr.array.set(_activeColors())
    // Highlight selected in bright white
    for (const i of indices) {
      attr.array[i*3] = 1; attr.array[i*3+1] = 1; attr.array[i*3+2] = 1
    }
    attr.needsUpdate = true
  }

  function applyLabelColor(indices, labelValue) {
    const [r, g, b] = paletteColor(labelValue)
    // Update classification color buffer
    for (const i of indices) {
      classificationColors[i*3] = r; classificationColors[i*3+1] = g; classificationColors[i*3+2] = b
    }
    // Switch to classification view automatically
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

  return { load, loading, pointCount, highlightIndices, applyLabelColor, resetColors, setViewMode, viewMode, getPositions, dispose }
}
