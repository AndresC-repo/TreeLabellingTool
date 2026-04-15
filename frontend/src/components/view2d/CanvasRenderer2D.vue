<template>
  <div ref="containerRef" class="canvas-container"
    @wheel.prevent="onWheel"
    @mousedown="onMouseDown"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @mouseleave="onMouseLeave"
  >
    <canvas ref="canvasRef" class="view-canvas"></canvas>
    <div v-if="loading" class="overlay-msg">Loading…</div>
    <div class="info-badge" v-if="pointCount > 0">
      {{ pointCount.toLocaleString() }} pts
      <span v-if="decimationRatio < 0.995" class="dim">
        ({{ Math.round(decimationRatio * 100) }}% of file)
      </span>
    </div>
    <div v-if="extractError" class="extract-error" @click="extractError = null">{{ extractError }}</div>
    <div class="point-size-ctrl">
      <button @click="changePointSize(-1)" :disabled="pointSize <= 1">−</button>
      <span>{{ pointSize }}px</span>
      <button @click="changePointSize(1)" :disabled="pointSize >= 8">+</button>
    </div>
    <!-- SVG overlay for selection drawing -->
    <svg class="svg-overlay"
      @mousedown="onSvgMouseDown"
      @mousemove="onSvgMouseMove"
      @mouseup="onSvgMouseUp"
      @click="onSvgClick"
      @contextmenu.prevent="onSvgContextMenu"
    >
      <rect
        v-if="store.activeTool === 'rectangle' && rectTool?.selecting?.value"
        :x="Math.min(rectTool.svgRect.x1, rectTool.svgRect.x2)"
        :y="Math.min(rectTool.svgRect.y1, rectTool.svgRect.y2)"
        :width="Math.abs(rectTool.svgRect.x2 - rectTool.svgRect.x1)"
        :height="Math.abs(rectTool.svgRect.y2 - rectTool.svgRect.y1)"
        fill="rgba(122,179,255,0.1)" stroke="#7ab3ff" stroke-width="1.5" stroke-dasharray="6,3"
      />
      <polyline
        v-if="store.activeTool === 'freehand' && freehandTool?.svgPoints?.value?.length > 0"
        :points="freehandTool.svgPoints.value.map(p => `${p.x},${p.y}`).join(' ')"
        fill="none" stroke="#ffd700" stroke-width="1.5"
      />
      <rect
        v-if="store.activeTool === 'fixed' && fixedTool?.hasRect?.value"
        :x="Math.min(fixedTool.svgRect.x1, fixedTool.svgRect.x2)"
        :y="Math.min(fixedTool.svgRect.y1, fixedTool.svgRect.y2)"
        :width="Math.abs(fixedTool.svgRect.x2 - fixedTool.svgRect.x1)"
        :height="Math.abs(fixedTool.svgRect.y2 - fixedTool.svgRect.y1)"
        fill="rgba(255,165,0,0.1)" stroke="#ffa500" stroke-width="1.5" stroke-dasharray="4,4"
      />
      <rect
        v-if="store.activeTool === 'fixed' && fixedTool?.isDrawing?.value"
        :x="Math.min(fixedTool?.svgRect?.x1 ?? 0, fixedTool?.svgRect?.x2 ?? 0)"
        :y="Math.min(fixedTool?.svgRect?.y1 ?? 0, fixedTool?.svgRect?.y2 ?? 0)"
        :width="Math.abs((fixedTool?.svgRect?.x2 ?? 0) - (fixedTool?.svgRect?.x1 ?? 0))"
        :height="Math.abs((fixedTool?.svgRect?.y2 ?? 0) - (fixedTool?.svgRect?.y1 ?? 0))"
        fill="rgba(255,165,0,0.05)" stroke="#ffa50080" stroke-width="1" stroke-dasharray="4,4"
      />
    </svg>
  </div>
</template>

<script setup>
import { ref, shallowRef, reactive, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useView2DStore } from '../../stores/view2d.js'
import { useSelectionRect } from '../../composables/useSelectionRect.js'
import { useSelectionFreehand } from '../../composables/useSelectionFreehand.js'
import { useFixedRect } from '../../composables/useFixedRect.js'
import { get2DImage, extractPatch } from '../../api/client.js'

const route = useRoute()
const sessionId = route.params.id
const store = useView2DStore()

const containerRef = ref(null)
const canvasRef = ref(null)
const loading = ref(false)
const pointCount = ref(0)
const decimationRatio = ref(1)
const extractError = ref(null)

// Image state
let currentImage = null
let IMG_W = 2048, IMG_H = 2048
const pointSize = ref(4)
const bounds = reactive({ xmin: 0, xmax: 1, ymin: 0, ymax: 1 })
const pan = reactive({ offsetX: 0, offsetY: 0, scale: 1 })

// ── Coordinate mapping ───────────────────────────────────────────────────────

function toWorld(clientX, clientY) {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const r = canvas.getBoundingClientRect()
  const imgX = (clientX - r.left - pan.offsetX) / pan.scale
  const imgY = (clientY - r.top  - pan.offsetY) / pan.scale
  return {
    x: bounds.xmin + (imgX / IMG_W) * (bounds.xmax - bounds.xmin),
    y: bounds.ymax - (imgY / IMG_H) * (bounds.ymax - bounds.ymin),
  }
}

function worldToCanvas(wx, wy) {
  const imgX = (wx - bounds.xmin) / (bounds.xmax - bounds.xmin) * IMG_W
  const imgY = (bounds.ymax - wy) / (bounds.ymax - bounds.ymin) * IMG_H
  return { x: pan.offsetX + imgX * pan.scale, y: pan.offsetY + imgY * pan.scale }
}

// ── Canvas drawing ───────────────────────────────────────────────────────────

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = '#1a1a2e'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  if (currentImage) {
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(currentImage, pan.offsetX, pan.offsetY, IMG_W * pan.scale, IMG_H * pan.scale)
  }
  drawHatches(ctx)
}

function drawHatches(ctx) {
  for (const region of store.labeledRegions) {
    if (region.selection_type === 'rectangle' && region.bounds_2d) {
      const b = region.bounds_2d
      const c = [
        worldToCanvas(b.x_min, b.y_min), worldToCanvas(b.x_max, b.y_min),
        worldToCanvas(b.x_max, b.y_max), worldToCanvas(b.x_min, b.y_max),
      ]
      ctx.beginPath()
      ctx.moveTo(c[0].x, c[0].y)
      for (let i = 1; i < c.length; i++) ctx.lineTo(c[i].x, c[i].y)
      ctx.closePath()
      ctx.fillStyle = 'rgba(100,180,255,0.18)'
      ctx.fill()
      ctx.strokeStyle = 'rgba(100,200,255,0.6)'
      ctx.lineWidth = 1.5
      ctx.stroke()
    } else if (region.selection_type === 'polygon' && region.polygon_2d?.length) {
      const c = region.polygon_2d.map(([wx, wy]) => worldToCanvas(wx, wy))
      ctx.beginPath()
      ctx.moveTo(c[0].x, c[0].y)
      for (let i = 1; i < c.length; i++) ctx.lineTo(c[i].x, c[i].y)
      ctx.closePath()
      ctx.fillStyle = 'rgba(255,215,0,0.15)'
      ctx.fill()
      ctx.strokeStyle = 'rgba(255,215,0,0.7)'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
  }
}

function fitImage() {
  const canvas = canvasRef.value
  if (!canvas) return
  const scale = Math.min(canvas.width / IMG_W, canvas.height / IMG_H) * 0.95
  pan.scale   = scale
  pan.offsetX = (canvas.width  - IMG_W * scale) / 2
  pan.offsetY = (canvas.height - IMG_H * scale) / 2
}

function syncCanvasSize() {
  const canvas     = canvasRef.value
  const container  = containerRef.value
  if (!canvas || !container) return
  canvas.width  = container.clientWidth
  canvas.height = container.clientHeight
  draw()
}

// ── Image loading ────────────────────────────────────────────────────────────

function changePointSize(delta) {
  const next = Math.max(1, Math.min(8, pointSize.value + delta))
  if (next === pointSize.value) return
  pointSize.value = next
  loadField(store.scalarField || 'classification')
}

async function loadField(field) {
  loading.value = true
  try {
    const res = await get2DImage(sessionId, field, pointSize.value)
    const h = res.headers
    bounds.xmin = parseFloat(h['x-bounds-xmin'])
    bounds.xmax = parseFloat(h['x-bounds-xmax'])
    bounds.ymin = parseFloat(h['x-bounds-ymin'])
    bounds.ymax = parseFloat(h['x-bounds-ymax'])
    IMG_W = parseInt(h['x-image-width']  ?? '2048')
    IMG_H = parseInt(h['x-image-height'] ?? '2048')
    pointCount.value      = parseInt(h['x-point-count']       ?? '0')
    decimationRatio.value = parseFloat(h['x-decimation-ratio'] ?? '1')

    const url = URL.createObjectURL(res.data)
    const img = new window.Image()
    img.onload = () => {
      if (currentImage) URL.revokeObjectURL(currentImage.src)
      currentImage = img
      fitImage()
      draw()
    }
    img.src = url
  } catch (err) {
    console.error('Failed to load 2D image:', err)
  } finally {
    loading.value = false
  }
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

let resizeObserver = null

onMounted(async () => {
  syncCanvasSize()
  resizeObserver = new ResizeObserver(syncCanvasSize)
  resizeObserver.observe(containerRef.value)
  await loadField(store.scalarField || 'elevation')
  await nextTick()
  const domRef = ref(canvasRef.value)
  rectTool.value     = useSelectionRect(toWorld, domRef)
  freehandTool.value = useSelectionFreehand(toWorld, domRef)
  fixedTool.value    = useFixedRect(toWorld, domRef)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  if (currentImage) URL.revokeObjectURL(currentImage.src)
})

watch(() => store.scalarField, field => loadField(field))
watch(() => store.labeledRegions, () => draw(), { deep: true })

// ── Selection tools (assigned after mount) ───────────────────────────────────

const rectTool     = shallowRef(null)
const freehandTool = shallowRef(null)
const fixedTool    = shallowRef(null)

// ── Pan (middle mouse / Alt+left) ───────────────────────────────────────────

let isPanning = false, lastX = 0, lastY = 0

function onMouseDown(e) {
  if (e.button === 1 || (e.button === 0 && (e.altKey || e.ctrlKey))) {
    isPanning = true; lastX = e.clientX; lastY = e.clientY; e.preventDefault()
  }
}
function onMouseMove(e) {
  if (!isPanning) return
  pan.offsetX += e.clientX - lastX
  pan.offsetY += e.clientY - lastY
  lastX = e.clientX; lastY = e.clientY
  draw()
}
function onMouseUp()    { isPanning = false }
function onMouseLeave() { isPanning = false }

function onWheel(e) {
  const factor   = e.deltaY > 0 ? 1 / 1.15 : 1.15
  const newScale = Math.max(0.01, pan.scale * factor)
  const canvas   = canvasRef.value
  const r        = canvas.getBoundingClientRect()
  const cx = e.clientX - r.left
  const cy = e.clientY - r.top
  pan.offsetX = cx - (cx - pan.offsetX) * (newScale / pan.scale)
  pan.offsetY = cy - (cy - pan.offsetY) * (newScale / pan.scale)
  pan.scale   = newScale
  draw()
}

// ── SVG event routing ────────────────────────────────────────────────────────

function onSvgMouseDown(e) {
  if (e.button === 1 || (e.button === 0 && (e.altKey || e.ctrlKey))) return
  if (store.activeTool === 'rectangle') rectTool.value?.onMouseDown(e)
  else if (store.activeTool === 'fixed') fixedTool.value?.onMouseDown(e)
}
function onSvgMouseMove(e) {
  if (store.activeTool === 'rectangle') rectTool.value?.onMouseMove(e)
  else if (store.activeTool === 'fixed') fixedTool.value?.onMouseMove(e)
}
async function onSvgMouseUp(e) {
  if (e.button === 1 || (e.button === 0 && (e.altKey || e.ctrlKey))) return
  if (store.activeTool === 'rectangle') {
    const b = rectTool.value?.onMouseUp(e)
    if (b) await doExtract('rectangle', b, null)
  } else if (store.activeTool === 'fixed') {
    const b = fixedTool.value?.onMouseUp(e)
    if (b) await doExtract('rectangle', b, null)
  }
}
function onSvgClick(e) {
  if (store.activeTool === 'freehand') freehandTool.value?.onClick(e)
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
      patch_id:       res.data.patch_id,
      patch_number:   res.data.patch_number,
      point_count:    res.data.point_count,
      selection_type: selectionType,
      bounds_2d:      bounds2d,
      polygon_2d:     polygon2d,
    })
    draw()
  } catch (err) {
    console.error('Patch extraction failed:', err)
    extractError.value = err.response?.data?.detail || 'No points found in selection — try a larger area'
  }
}
</script>

<style scoped>
.canvas-container {
  position: relative; width: 100%; height: 100%; overflow: hidden;
  cursor: grab;
}
.canvas-container:active { cursor: grabbing; }
.view-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
.overlay-msg {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  color: #adf; font-size: 1.1rem; pointer-events: none;
}
.info-badge {
  position: absolute; top: 10px; right: 12px;
  background: rgba(0,0,0,0.6); color: #cce;
  padding: 3px 10px; border-radius: 8px; font-size: 12px; pointer-events: none;
}
.dim { opacity: 0.7; margin-left: 4px; }
.point-size-ctrl {
  position: absolute; bottom: 12px; right: 12px; z-index: 10;
  display: flex; align-items: center; gap: 6px;
  background: rgba(0,0,0,0.6); padding: 4px 8px;
  border-radius: 8px; pointer-events: all;
}
.point-size-ctrl button {
  background: #2a3a5a; border: 1px solid #445; color: #eee;
  width: 24px; height: 24px; border-radius: 4px;
  cursor: pointer; font-size: 16px; line-height: 1;
  display: flex; align-items: center; justify-content: center;
}
.point-size-ctrl button:hover:not(:disabled) { background: #3a4a7a; }
.point-size-ctrl button:disabled { opacity: 0.35; cursor: default; }
.point-size-ctrl span { color: #cce; font-size: 12px; min-width: 28px; text-align: center; }
.svg-overlay {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  pointer-events: all; z-index: 5;
}
.extract-error {
  position: absolute; bottom: 50px; left: 50%; transform: translateX(-50%);
  background: rgba(180,40,40,0.9); color: #fff; padding: 8px 18px;
  border-radius: 8px; font-size: 13px; cursor: pointer; z-index: 20;
  max-width: 80%; text-align: center;
}
</style>
