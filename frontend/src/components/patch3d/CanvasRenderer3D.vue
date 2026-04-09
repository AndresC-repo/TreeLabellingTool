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
        <button :class="{ active: rotateMode }" @click="setRotate(true)" title="Rotate / pan view">&#8635; Rotate</button>
        <button :class="{ active: !rotateMode }" @click="setRotate(false)" title="Draw lasso selection">&#9684; Select</button>
      </div>
      <div class="btn-group">
        <button :class="{ active: store.viewMode === 'elevation' }" @click="store.viewMode = 'elevation'">Elevation</button>
        <button :class="{ active: store.viewMode === 'classification' }" @click="store.viewMode = 'classification'">Classification</button>
      </div>
      <div class="btn-group">
        <button @click="setTopView" title="Top view (Z down)">&#9651; Top</button>
        <button @click="setSideView" title="Side view">&#9654; Side</button>
      </div>
    </div>
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
import { useRoute } from 'vue-router'
import { useLasso3D } from '../../composables/useLasso3D.js'
import LassoOverlay from './LassoOverlay.vue'

const container = ref(null)
const axisCanvas = ref(null)
const route = useRoute()
const store = usePatch3DStore()

const { scene, camera, renderer, setOnFrame } = useThreeScene(container, 'perspective')
const pc3d = usePointCloud3D(scene, route.params.id, route.params.patchId)
const { load, loading, pointCount, highlightIndices, applyLabelColor, resetColors, setViewMode, getPositions, dispose } = pc3d

const lasso = useLasso3D(camera, renderer)

let controls = null
let axisRenderer = null
let axisScene = null
let axisCamera = null
let axisAnimId = null
const rotateMode = ref(true)
let cloudCenter = null
let cloudSpan = 1

function setTopView() {
  if (!cloudCenter || !controls || !camera.value) return
  const { x, y, z } = cloudCenter
  camera.value.position.set(x, y, z + cloudSpan * 2)
  camera.value.up.set(0, 1, 0)
  camera.value.lookAt(x, y, z)
  controls.target.set(x, y, z)
  controls.update()
}

function setSideView() {
  if (!cloudCenter || !controls || !camera.value) return
  const { x, y, z } = cloudCenter
  camera.value.position.set(x, y - cloudSpan * 2, z)
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

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  const result = await load()
  store.pointCount = pointCount.value

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
  controls?.dispose()
  if (axisAnimId) cancelAnimationFrame(axisAnimId)
  axisRenderer?.dispose()
  dispose()
})

defineExpose({ highlightIndices, applyLabelColor, resetColors, getPositions, camera, renderer })
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

.axis-triad {
  position: absolute; bottom: 16px; left: 16px;
  width: 96px; height: 96px;
  pointer-events: none; z-index: 10;
  border-radius: 8px;
  background: rgba(0,0,0,0.3);
}
</style>
