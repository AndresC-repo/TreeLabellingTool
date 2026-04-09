<template>
  <div ref="containerRef" class="canvas-container">
    <div v-if="loading" class="overlay-msg">Loading point cloud…</div>
    <div class="info-badge" v-if="pointCount > 0">
      {{ pointCount.toLocaleString() }} pts
      <span v-if="decimationRatio < 0.995" class="dim">
        ({{ Math.round(decimationRatio * 100) }}% of file)
      </span>
    </div>
    <!-- SVG overlay: selection drawing -->
    <svg
      ref="svgRef"
      class="svg-overlay"
      @mousedown="onSvgMouseDown"
      @mousemove="onSvgMouseMove"
      @mouseup="onSvgMouseUp"
      @click="onSvgClick"
      @contextmenu.prevent="onSvgContextMenu"
    >
      <!-- Rectangle selection indicator -->
      <rect
        v-if="store.activeTool === 'rectangle' && rectTool?.selecting?.value"
        :x="Math.min(rectTool.svgRect.x1, rectTool.svgRect.x2)"
        :y="Math.min(rectTool.svgRect.y1, rectTool.svgRect.y2)"
        :width="Math.abs(rectTool.svgRect.x2 - rectTool.svgRect.x1)"
        :height="Math.abs(rectTool.svgRect.y2 - rectTool.svgRect.y1)"
        fill="rgba(122,179,255,0.1)"
        stroke="#7ab3ff"
        stroke-width="1.5"
        stroke-dasharray="6,3"
      />
      <!-- Freehand polygon indicator -->
      <polyline
        v-if="store.activeTool === 'freehand' && freehandTool?.svgPoints?.value?.length > 0"
        :points="freehandTool.svgPoints.value.map(p => `${p.x},${p.y}`).join(' ')"
        fill="none"
        stroke="#ffd700"
        stroke-width="1.5"
      />
      <!-- Fixed rectangle indicator -->
      <rect
        v-if="store.activeTool === 'fixed' && fixedTool?.hasRect?.value"
        :x="Math.min(fixedTool.svgRect.x1, fixedTool.svgRect.x2)"
        :y="Math.min(fixedTool.svgRect.y1, fixedTool.svgRect.y2)"
        :width="Math.abs(fixedTool.svgRect.x2 - fixedTool.svgRect.x1)"
        :height="Math.abs(fixedTool.svgRect.y2 - fixedTool.svgRect.y1)"
        fill="rgba(255,165,0,0.1)"
        stroke="#ffa500"
        stroke-width="1.5"
        stroke-dasharray="4,4"
      />
      <!-- Fixed rect in-progress drawing (before hasRect) -->
      <rect
        v-if="store.activeTool === 'fixed' && fixedTool?.isDrawing?.value"
        :x="Math.min(fixedTool?.svgRect?.x1 ?? 0, fixedTool?.svgRect?.x2 ?? 0)"
        :y="Math.min(fixedTool?.svgRect?.y1 ?? 0, fixedTool?.svgRect?.y2 ?? 0)"
        :width="Math.abs((fixedTool?.svgRect?.x2 ?? 0) - (fixedTool?.svgRect?.x1 ?? 0))"
        :height="Math.abs((fixedTool?.svgRect?.y2 ?? 0) - (fixedTool?.svgRect?.y1 ?? 0))"
        fill="rgba(255,165,0,0.05)"
        stroke="#ffa50080"
        stroke-width="1"
        stroke-dasharray="4,4"
      />
    </svg>
    <!-- Hatch canvas: labeled region overlays -->
    <canvas ref="hatchRef" class="hatch-overlay"></canvas>
  </div>
</template>

<script setup>
import * as THREE from 'three'
import { ref, shallowRef, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useThreeScene } from '../../composables/useThreeScene.js'
import { usePointCloud2D } from '../../composables/usePointCloud2D.js'
import { useView2DStore } from '../../stores/view2d.js'
import { useSelectionRect } from '../../composables/useSelectionRect.js'
import { useSelectionFreehand } from '../../composables/useSelectionFreehand.js'
import { useFixedRect } from '../../composables/useFixedRect.js'
import { extractPatch } from '../../api/client.js'

const route = useRoute()
const sessionId = route.params.id
const containerRef = ref(null)
const svgRef = ref(null)
const hatchRef = ref(null)
const loading = ref(false)
const pointCount = ref(0)
const decimationRatio = ref(1)

const { scene, camera, renderer } = useThreeScene(containerRef, 'orthographic')
const { load, loading: pc2dLoading, pointCount: pc2dCount, decimationRatio: pc2dRatio, dispose } = usePointCloud2D(scene, sessionId)
const store = useView2DStore()

watch(pc2dLoading, v => { loading.value = v })
watch(pc2dCount,   v => { pointCount.value = v })
watch(pc2dRatio,   v => { decimationRatio.value = v })

onMounted(async () => {
  const center = await load('classification')
  if (center && camera.value) {
    camera.value.position.set(center.x, center.y, 100)
    camera.value.lookAt(center.x, center.y, 0)
  }

  const el = containerRef.value
  el.addEventListener('mousedown', onContainerMouseDown)
  el.addEventListener('mousemove', onContainerMouseMove)
  el.addEventListener('mouseup',   onContainerMouseUp)
  el.addEventListener('mouseleave', endPan)
  el.addEventListener('wheel',     onWheel, { passive: false })
})

onBeforeUnmount(() => dispose())

watch(() => store.scalarField, async field => {
  isPanning = false
  const center = await load(field)
  if (center && camera.value) {
    camera.value.position.set(center.x, center.y, 100)
    camera.value.lookAt(center.x, center.y, 0)
  }
})

// ── Selection composables (need renderer.domElement once it's ready) ────────
// We lazily initialize them in onMounted because renderer.domElement requires init
const rectTool = shallowRef(null)
const freehandTool = shallowRef(null)
const fixedTool = shallowRef(null)

// After Three.js init, wire up selection composables
onMounted(() => {
  // renderer.value is available after useThreeScene's onMounted runs
  // We defer by one tick to be safe
  nextTick(() => {
    const domRef = ref(renderer.value?.domElement)
    rectTool.value     = useSelectionRect(camera, domRef)
    freehandTool.value = useSelectionFreehand(camera, domRef)
    fixedTool.value    = useFixedRect(camera, domRef)
  })
})

// SVG event routing
async function onSvgMouseDown(e) {
  if (e.button === 1 || (e.button === 0 && e.altKey)) return
  if (store.activeTool === 'rectangle') rectTool.value?.onMouseDown(e)
  else if (store.activeTool === 'fixed') fixedTool.value?.onMouseDown(e)
}

function onSvgMouseMove(e) {
  if (store.activeTool === 'rectangle') rectTool.value?.onMouseMove(e)
  else if (store.activeTool === 'fixed') fixedTool.value?.onMouseMove(e)
}

async function onSvgMouseUp(e) {
  if (e.button === 1 || (e.button === 0 && e.altKey)) return
  if (store.activeTool === 'rectangle') {
    const bounds = rectTool.value?.onMouseUp(e)
    if (bounds) await doExtract('rectangle', bounds, null)
  } else if (store.activeTool === 'fixed') {
    const bounds = fixedTool.value?.onMouseUp(e)
    if (bounds) await doExtract('rectangle', bounds, null)
  }
}

async function onSvgClick(e) {
  if (store.activeTool !== 'freehand') return
  freehandTool.value?.onClick(e)
}

async function onSvgContextMenu(e) {
  if (store.activeTool !== 'freehand') return
  const polygon = freehandTool.value?.onContextMenu(e)
  if (polygon) await doExtract('polygon', null, polygon)
}

async function doExtract(selectionType, bounds2d, polygon2d) {
  try {
    const payload = { selection_type: selectionType }
    if (bounds2d)  payload.bounds_2d  = bounds2d
    if (polygon2d) payload.polygon_2d = polygon2d
    const res = await extractPatch(sessionId, payload)
    store.addRegion({
      patch_id: res.data.patch_id,
      point_count: res.data.point_count,
      selection_type: selectionType,
      bounds_2d: bounds2d,
      polygon_2d: polygon2d,
    })
    drawHatchOverlay()
  } catch (err) {
    console.error('Patch extraction failed:', err)
  }
}

function drawHatchOverlay() {
  const canvas = hatchRef.value
  if (!canvas) return
  canvas.width  = canvas.offsetWidth
  canvas.height = canvas.offsetHeight
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  for (const region of store.labeledRegions) {
    if (region.selection_type === 'rectangle' && region.bounds_2d) {
      // Convert world-space bounds back to screen space for hatching
      const screenCorners = [
        worldToScreen(region.bounds_2d.x_min, region.bounds_2d.y_min),
        worldToScreen(region.bounds_2d.x_max, region.bounds_2d.y_min),
        worldToScreen(region.bounds_2d.x_max, region.bounds_2d.y_max),
        worldToScreen(region.bounds_2d.x_min, region.bounds_2d.y_max),
      ]
      ctx.beginPath()
      ctx.moveTo(screenCorners[0].x, screenCorners[0].y)
      for (let i = 1; i < screenCorners.length; i++) ctx.lineTo(screenCorners[i].x, screenCorners[i].y)
      ctx.closePath()
      ctx.fillStyle = 'rgba(100, 180, 255, 0.18)'
      ctx.fill()
      ctx.strokeStyle = 'rgba(100, 200, 255, 0.6)'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
  }
}

function worldToScreen(wx, wy) {
  if (!camera.value || !renderer.value) return { x: 0, y: 0 }
  const vec = new THREE.Vector3(wx, wy, 0)
  vec.project(camera.value)
  const w = renderer.value.domElement.clientWidth
  const h = renderer.value.domElement.clientHeight
  return {
    x: ((vec.x + 1) / 2) * w,
    y: ((1 - vec.y) / 2) * h,
  }
}

// ── Pan (middle mouse / Alt+drag) — on the container, not the SVG ──────────
let isPanning = false, lastX = 0, lastY = 0

function onContainerMouseDown(e) {
  if (e.button === 1 || (e.button === 0 && e.altKey)) {
    isPanning = true
    lastX = e.clientX; lastY = e.clientY
    e.preventDefault()
  }
}
function onContainerMouseMove(e) {
  if (!isPanning || !camera.value) return
  const dx = e.clientX - lastX
  const dy = e.clientY - lastY
  camera.value.position.x -= dx / camera.value.zoom
  camera.value.position.y += dy / camera.value.zoom
  lastX = e.clientX; lastY = e.clientY
  drawHatchOverlay()
}
function onContainerMouseUp()  { isPanning = false }
function endPan()              { isPanning = false }

function onWheel(e) {
  if (!camera.value) return
  e.preventDefault()
  const factor = e.deltaY > 0 ? 1 / 1.1 : 1.1
  camera.value.zoom = Math.max(0.001, camera.value.zoom * factor)
  camera.value.updateProjectionMatrix()
  drawHatchOverlay()
}
</script>

<style scoped>
.canvas-container {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.overlay-msg {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  color: #adf;
  font-size: 1.1rem;
  pointer-events: none;
}
.info-badge {
  position: absolute;
  top: 10px; right: 12px;
  background: rgba(0,0,0,0.6);
  color: #cce;
  padding: 3px 10px;
  border-radius: 8px;
  font-size: 12px;
  pointer-events: none;
}
.dim { opacity: 0.7; margin-left: 4px; }
.svg-overlay {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  pointer-events: all;
}
.hatch-overlay {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  pointer-events: none;
}
</style>
