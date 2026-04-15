<template>
  <div ref="container" class="canvas3d">
    <div v-if="loading" class="loading">Loading patch...</div>
    <LassoOverlay
      :drawing="lasso.drawing.value"
      :lassoPoints="lasso.lassoPoints.value"
      :processing="lasso.processing.value"
      :rotateMode="rotateMode"
      @addVertex="lasso.addVertex"
      @finish="onLassoFinish"
      @cancel="lasso.cancelLasso"
    />
    <div class="toolbar-overlay">
      <div class="btn-group">
        <button :class="{ active: rotateMode }"  @click="setRotate(true)"  title="Rotate / pan view">&#8635; Rotate</button>
        <button :class="{ active: !rotateMode }" @click="setRotate(false)" title="Draw lasso selection [R]">&#9684; Select <kbd>R</kbd></button>
      </div>
      <div class="btn-group">
        <button :class="{ active: store.viewMode === 'classification' }" @click="store.viewMode = 'classification'" title="Labels view [L]">Labels <kbd>L</kbd></button>
      </div>
      <div class="btn-group inference-dropdown-wrap" ref="inferenceWrap">
        <button
          :class="{ active: store.viewMode === 'prediction' }"
          :disabled="store.predicting"
          @click="inferenceOpen = !inferenceOpen"
          title="Inference — choose model [I]"
        >
          {{ store.predicting ? '…' : 'Inference' }}
          <span v-if="store.inferenceVersion" class="inf-ver">({{ inferenceVersions.find(v => v.id === store.inferenceVersion)?.label }})</span>
          <kbd>I</kbd> ▾
        </button>
        <div v-if="inferenceOpen" class="inference-menu">
          <button
            v-for="v in inferenceVersions" :key="v.id"
            :class="{ active: store.inferenceVersion === v.id && store.viewMode === 'prediction' }"
            :disabled="store.predicting"
            @click="selectInference(v.id)"
            :title="v.title"
          >{{ v.label }}<span class="inf-desc">{{ v.desc }}</span></button>
        </div>
      </div>
      <div class="btn-group">
        <button :class="{ active: store.viewMode === 'elevation' }" @click="store.viewMode = 'elevation'" title="Elevation view [V]">Elevation <kbd>V</kbd></button>
        <button :class="{ active: store.viewMode === 'dtm' }"       @click="store.viewMode = 'dtm'"       title="DTM — terrain min Z per cell [V]">DTM <kbd>V</kbd></button>
        <button :class="{ active: store.viewMode === 'chm' }"       @click="store.viewMode = 'chm'"       title="CHM — height above ground [V]">CHM <kbd>V</kbd></button>
      </div>
      <div class="btn-group">
        <button @click="setTopView"  title="Top view [T]">&#9651; Top <kbd>T</kbd></button>
        <button @click="setSideView" title="Side view [S]">&#9654; Side <kbd>S</kbd></button>
      </div>
    </div>
    <!-- Elevation Z filter slider (only in elevation view) -->
    <ElevationFilter
      v-if="store.viewMode === 'elevation'"
      :zMin="store.zBoundsMin"
      :zMax="store.zBoundsMax"
      :modelValueLo="store.elevFilterMin"
      :modelValueHi="store.elevFilterMax"
      :labelValue="store.nextLabel"
      @update:modelValueLo="store.elevFilterMin = $event"
      @update:modelValueHi="store.elevFilterMax = $event"
      @label-inside="onLabelInside"
      @gnd-below="onGndBelow"
    />
    <!-- Corner axis triad -->
    <canvas ref="axisCanvas" class="axis-triad"></canvas>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as THREE from 'three'
import { TrackballControls } from 'three/addons/controls/TrackballControls.js'
import { useThreeScene } from '../../composables/useThreeScene.js'
import { usePointCloud3D } from '../../composables/usePointCloud3D.js'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useView2DStore } from '../../stores/view2d.js'
import { useRoute } from 'vue-router'
import { useLasso3D } from '../../composables/useLasso3D.js'
import { labelPoints, getNextLabel, predictPatch } from '../../api/client.js'
import LassoOverlay from './LassoOverlay.vue'
import ElevationFilter from './ElevationFilter.vue'

const container = ref(null)
const axisCanvas = ref(null)
const route = useRoute()
const store = usePatch3DStore()
const view2d = useView2DStore()

const { scene, camera, renderer, setOnFrame } = useThreeScene(container, 'perspective')
const pc3d = usePointCloud3D(scene, route.params.id, route.params.patchId)
const { load, loading, pointCount, highlightIndices, applyLabelColor, applyPredictionColors, resetColors, setViewMode, getPositions, setElevationFilter, dispose } = pc3d

const lasso = useLasso3D(camera, renderer)

const inferenceVersions = [
  { id: 'v1', label: 'XYZ',     desc: 'Coordinates only',                   title: 'Inference — XYZ only [I]' },
  { id: 'v2', label: 'XYZ+C',   desc: 'XYZ + Classification',               title: 'Inference — XYZ + Classification' },
  { id: 'v3', label: 'XYZ+I',   desc: 'XYZ + Intensity',                    title: 'Inference — XYZ + Intensity' },
  { id: 'v4', label: 'XYZ+I+C', desc: 'XYZ + Intensity + Classification',   title: 'Inference — XYZ + Intensity + Classification' },
]

const inferenceOpen = ref(false)
const inferenceWrap = ref(null)

function selectInference(version) {
  inferenceOpen.value = false
  runPrediction(version)
}

function onClickOutsideInference(e) {
  if (inferenceWrap.value && !inferenceWrap.value.contains(e.target)) {
    inferenceOpen.value = false
  }
}

let controls = null
let axisRenderer = null
let axisScene = null
let axisCamera = null
let axisAnimId = null
const rotateMode = ref(true)
let cloudCenter = null
let cloudSpan = 1
let lastView = null   // 'top' | 'side'
let sideSign = -1     // -1 = front face, +1 = back face

function setTopView() {
  if (!cloudCenter || !controls || !camera.value) return
  lastView = 'top'
  sideSign = -1       // reset side orientation when leaving side view
  const { x, y, z } = cloudCenter
  camera.value.position.set(x, y, z + cloudSpan * 2)
  camera.value.up.set(0, 1, 0)
  camera.value.lookAt(x, y, z)
  controls.target.set(x, y, z)
  controls.update()
}

function setSideView() {
  if (!cloudCenter || !controls || !camera.value) return
  if (lastView === 'side') sideSign *= -1   // flip 180° on repeated press
  else sideSign = -1
  lastView = 'side'
  const { x, y, z } = cloudCenter
  camera.value.position.set(x, y + sideSign * cloudSpan * 2, z)
  camera.value.up.set(0, 0, 1)
  camera.value.lookAt(x, y, z)
  controls.target.set(x, y, z)
  controls.update()
}

// ── Axis triad ───────────────────────────────────────────────────────────────

function setupAxisTriad() {
  const SIZE = 96
  axisScene = new THREE.Scene()

  axisCamera = new THREE.PerspectiveCamera(50, 1, 0.1, 100)
  axisCamera.position.set(0, 0, 3)

  // Axes: X=red, Y=green, Z=blue (Three.js default)
  axisScene.add(new THREE.AxesHelper(1.2))

  // Axis label sprites
  const labels = [
    { text: 'X', color: '#ff4444', pos: [1.5, 0, 0] },
    { text: 'Y', color: '#44ff44', pos: [0, 1.5, 0] },
    { text: 'Z', color: '#4488ff', pos: [0, 0, 1.5] },
  ]
  for (const { text, color, pos } of labels) {
    const canvas2d = document.createElement('canvas')
    canvas2d.width = 64; canvas2d.height = 64
    const ctx2d = canvas2d.getContext('2d')
    ctx2d.font = 'bold 44px sans-serif'
    ctx2d.fillStyle = color
    ctx2d.textAlign = 'center'
    ctx2d.textBaseline = 'middle'
    ctx2d.fillText(text, 32, 32)
    const tex = new THREE.CanvasTexture(canvas2d)
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }))
    sprite.position.set(...pos)
    sprite.scale.set(0.4, 0.4, 1)
    axisScene.add(sprite)
  }

  axisRenderer = new THREE.WebGLRenderer({ canvas: axisCanvas.value, alpha: true, antialias: true })
  axisRenderer.setPixelRatio(window.devicePixelRatio)
  axisRenderer.setSize(SIZE, SIZE)
  axisRenderer.setClearColor(0x000000, 0)

  function animateAxis() {
    axisAnimId = requestAnimationFrame(animateAxis)
    if (camera.value) {
      // Mirror main camera rotation but keep axis camera at fixed distance
      axisCamera.quaternion.copy(camera.value.quaternion)
    }
    axisRenderer.render(axisScene, axisCamera)
  }
  animateAxis()
}

// ── Controls ─────────────────────────────────────────────────────────────────

function setRotate(val) {
  rotateMode.value = val
  if (controls) controls.enabled = val
  if (val) lasso.cancelLasso()
}

function toggleRotate() {
  setRotate(!rotateMode.value)
}

// React to store viewMode changes (from view buttons or from LabelPanel)
watch(() => store.viewMode, mode => setViewMode(mode))

// React to a label being applied (from LabelPanel)
watch(() => store.lastApplied, applied => {
  if (!applied) return
  applyLabelColor(applied.indices, applied.labelValue)
})

async function onLassoFinish() {
  const positions = getPositions()
  if (!positions) return
  store.lassoProcessing = true
  try {
    const indices = await lasso.finishLasso(positions)
    if (indices.length === 0) return
    store.selectedIndices = indices
    highlightIndices(indices)
  } finally {
    store.lassoProcessing = false
  }
}

// ── Elevation filter label actions ────────────────────────────────────────────

// Palette colors — mirrors usePointCloud3D.js paletteColor()
function _paletteHex(labelValue) {
  let r, g, b
  if (labelValue === 0) { r = 0.28; g = 0.28; b = 0.32 }
  else if (labelValue >= 101 && labelValue <= 108) {
    const P = [[1,0,1],[0,1,1],[1,1,0],[1,.5,0],[.5,0,1],[0,1,.5],[1,0,.5],[.5,1,0]]
    ;[r, g, b] = P[labelValue - 101]
  } else {
    const h = ((labelValue * 137.508) % 360) / 360
    const s = 0.85, l = 0.55
    const q = l + s - l * s, p = 2 * l - q
    const hue2 = (t) => {
      if (t < 0) t += 1; if (t > 1) t -= 1
      if (t < 1/6) return p + (q-p)*6*t
      if (t < 1/2) return q
      if (t < 2/3) return p + (q-p)*(2/3-t)*6
      return p
    }
    r = hue2(h+1/3); g = hue2(h); b = hue2(h-1/3)
  }
  const hex = (v) => Math.round(Math.min(Math.max(v,0),1)*255).toString(16).padStart(2,'0')
  return `#${hex(r)}${hex(g)}${hex(b)}`
}

const INFERENCE_NAMES = { 0: 'Non-tree', 101: 'Tree' }

async function runPrediction(version = 'v1') {
  if (store.predicting) return
  store.predicting = true
  store.inferenceVersion = version
  try {
    const res = await predictPatch(route.params.id, route.params.patchId, version)
    const labels = res.data.labels
    applyPredictionColors(labels)
    store.viewMode = 'prediction'   // must come AFTER applyPredictionColors so predictionColors buffer exists
    store.hasPrediction = true
    store.inferenceLabels = labels  // keep raw array for "Apply to Labels"

    // Build legend: count occurrences of each label
    const counts = {}
    for (const lbl of labels) counts[lbl] = (counts[lbl] || 0) + 1
    store.predictionLegend = Object.entries(counts)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([lbl, count]) => ({
        label:  Number(lbl),
        name:   INFERENCE_NAMES[lbl] ?? `Class ${lbl}`,
        color:  _paletteHex(Number(lbl)),
        count,
      }))
  } catch (err) {
    console.error('Inference failed:', err)
  } finally {
    store.predicting = false
  }
}

async function onGndBelow() {
  const positions = getPositions()
  if (!positions) return
  const zThresh = store.elevFilterMin
  const count = store.pointCount
  const indices = []
  for (let i = 0; i < count; i++) {
    if (positions[i * 3 + 2] < zThresh) indices.push(i)
  }
  if (!indices.length) return
  try {
    await labelPoints(route.params.id, route.params.patchId, { point_indices: indices, label_value: 0 })
    store.lastApplied = { indices, labelValue: 0 }
    store.viewMode = 'classification'
    view2d.markLabelled(route.params.patchId)
  } catch (err) { console.error('GND below failed:', err) }
}

async function onLabelInside() {
  const positions = getPositions()
  if (!positions) return
  const zLo = store.elevFilterMin, zHi = store.elevFilterMax
  const lv = store.nextLabel
  const count = store.pointCount
  const indices = []
  for (let i = 0; i < count; i++) {
    const z = positions[i * 3 + 2]
    if (z >= zLo && z <= zHi) indices.push(i)
  }
  if (!indices.length) return
  try {
    await labelPoints(route.params.id, route.params.patchId, { point_indices: indices, label_value: lv })
    store.lastApplied = { indices, labelValue: lv }
    store.addAppliedLabel(lv)
    store.viewMode = 'classification'
    view2d.markLabelled(route.params.patchId)
    const res = await getNextLabel(route.params.id, route.params.patchId)
    store.nextLabel = res.data.next_label
  } catch (err) { console.error('Label inside failed:', err) }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

// React to elevation filter changes
watch(() => [store.elevFilterMin, store.elevFilterMax], ([lo, hi]) => {
  setElevationFilter(lo, hi)
})

onMounted(async () => {
  document.addEventListener('click', onClickOutsideInference, true)
  const result = await load()
  store.pointCount = pointCount.value

  if (result) {
    store.groundIndices = result.groundIndices ?? []
    store.zBoundsMin = result.zMin ?? 0
    store.zBoundsMax = result.zMax ?? 0
    store.elevFilterMin = result.zMin ?? 0
    store.elevFilterMax = result.zMax ?? 0
  }

  if (result?.center && camera.value) {
    const { center, positions } = result

    // Fit camera to bounding box
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, minZ = Infinity, maxZ = -Infinity
    for (let i = 0; i < positions.length; i += 3) {
      if (positions[i]   < minX) minX = positions[i];   if (positions[i]   > maxX) maxX = positions[i]
      if (positions[i+1] < minY) minY = positions[i+1]; if (positions[i+1] > maxY) maxY = positions[i+1]
      if (positions[i+2] < minZ) minZ = positions[i+2]; if (positions[i+2] > maxZ) maxZ = positions[i+2]
    }
    const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 1)
    cloudCenter = center
    cloudSpan = span
    const dist = span * 1.5
    camera.value.position.set(center.x, center.y - dist, center.z + dist * 0.5)
    camera.value.lookAt(center.x, center.y, center.z)
    camera.value.up.set(0, 0, 1)   // Z-up (matches LiDAR convention)

    // TrackballControls — arcball rotation, no gimbal lock
    controls = new TrackballControls(camera.value, renderer.value.domElement)
    controls.target.set(center.x, center.y, center.z)
    controls.rotateSpeed   = 3.0
    controls.zoomSpeed     = 1.2
    controls.panSpeed      = 0.8
    controls.staticMoving  = true   // no inertia (matches CloudCompare)
    controls.enabled = rotateMode.value
    controls.update()

    // TrackballControls must be updated every frame
    setOnFrame(() => { if (controls?.enabled) controls.update() })
  }

  setupAxisTriad()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutsideInference, true)
  controls?.dispose()
  if (axisAnimId) cancelAnimationFrame(axisAnimId)
  axisRenderer?.dispose()
  dispose()
})

defineExpose({ highlightIndices, applyLabelColor, resetColors, getPositions, camera, renderer, setRotate, toggleRotate, setTopView, setSideView, runPrediction })
</script>

<style scoped>
.canvas3d { position: relative; width: 100%; height: 100%; }
.loading { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); color: #adf; font-size: 1.2rem; }

.toolbar-overlay {
  position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 8px; z-index: 10;
  background: rgba(0,0,0,0.6); padding: 4px 6px; border-radius: 8px;
  pointer-events: all;
}
.btn-group { display: flex; gap: 3px; }
.btn-group + .btn-group { border-left: 1px solid #445; padding-left: 8px; }
.toolbar-overlay button {
  background: #2a3a5a; color: #aac; border: 1px solid #445;
  padding: 5px 12px; border-radius: 5px; cursor: pointer; font-size: 12px;
}
.toolbar-overlay button.active { background: #3a5a8e; color: #fff; border-color: #7ab3ff; }
.toolbar-overlay button:hover:not(.active) { background: #344; color: #eee; }
.toolbar-overlay kbd {
  display: inline-block; font-size: 9px; font-family: monospace;
  background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.2);
  border-radius: 3px; padding: 0 3px; margin-left: 3px;
  line-height: 1.6; color: #aac; vertical-align: middle;
}

.inference-dropdown-wrap { position: relative; }
.inf-ver { font-size: 10px; color: #88a; margin-left: 3px; }
.inference-menu {
  position: absolute; top: calc(100% + 4px); left: 0;
  background: #1a1a2e; border: 1px solid #445;
  border-radius: 6px; overflow: hidden;
  display: flex; flex-direction: column;
  min-width: 200px; z-index: 100;
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
}
.inference-menu button {
  display: flex; flex-direction: column; align-items: flex-start;
  padding: 8px 12px; border-radius: 0; border: none;
  border-bottom: 1px solid #2a3a5a; background: #1e2840;
  text-align: left; gap: 2px;
}
.inference-menu button:last-child { border-bottom: none; }
.inference-menu button:hover:not(.active):not(:disabled) { background: #2a3a5a; }
.inference-menu button.active { background: #3a5a8e; color: #fff; }
.inf-desc { font-size: 10px; color: #667; font-weight: normal; }
.inference-menu button.active .inf-desc { color: #99c; }

.axis-triad {
  position: absolute; bottom: 16px; left: 16px;
  width: 96px; height: 96px;
  pointer-events: none; z-index: 10;
  border-radius: 8px;
  background: rgba(0,0,0,0.3);
}
</style>
