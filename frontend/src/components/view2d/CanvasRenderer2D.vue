<template>
  <div ref="containerRef" class="canvas-container"
    @wheel.prevent="onWheel"
    @mousedown="onMouseDown"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @mouseleave="onMouseLeave"
    @contextmenu.prevent
  >
    <canvas ref="canvasRef" class="view-canvas"></canvas>
    <div v-if="loading && !loadError" class="overlay-msg">Loading…</div>
    <div v-if="loadError" class="load-error" @mousedown.stop @click.stop>
      <p class="load-error-title">Couldn't load the 2D view</p>
      <p class="load-error-detail">{{ loadError }}</p>
      <button @click="loadField(store.scalarField || 'elevation')">Retry</button>
    </div>
    <div class="info-badge" v-if="pointCount > 0 && !loadError">
      <template v-if="detail">
        {{ detail.pointCount.toLocaleString() }} pts in view
        <span class="dim">{{ detail.ratio < 0.995 ? `(${Math.round(detail.ratio * 100)}% of points here)` : '(full detail)' }}</span>
      </template>
      <template v-else>
        {{ pointCount.toLocaleString() }} pts
        <span v-if="decimationRatio < 0.995" class="dim">
          ({{ Math.round(decimationRatio * 100) }}% of file{{ decimationRatio < 0.995 ? ' — zoom in for full detail' : '' }})
        </span>
      </template>
      <span v-if="refining" class="dim"> · refining…</span>
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

const loadError = ref(null)

// Image state — overview of the whole file (decimated sample)
let currentImage = null
let IMG_W = 2048, IMG_H = 2048
const pointSize = ref(4)

// Zoomed-in image of the visible area at full point density, drawn over the overview
// { img, bounds: {xmin,xmax,ymin,ymax}, pointCount, ratio }
const detail = shallowRef(null)
const refining = ref(false)
let detailAbort = null
let detailTimer = null
let overviewToken = 0
let pointSizeTimer = null
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
  const d = detail.value
  if (d) {
    const tl = worldToCanvas(d.bounds.xmin, d.bounds.ymax)
    const br = worldToCanvas(d.bounds.xmax, d.bounds.ymin)
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(d.img, tl.x, tl.y, br.x - tl.x, br.y - tl.y)
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
  scheduleDetail()
}

// ── Image loading ────────────────────────────────────────────────────────────

function changePointSize(delta) {
  const next = Math.max(1, Math.min(8, pointSize.value + delta))
  if (next === pointSize.value) return
  pointSize.value = next
  // Wait until the clicking stops, then re-render once
  clearTimeout(pointSizeTimer)
  pointSizeTimer = setTimeout(() => loadField(store.scalarField || 'elevation', { keepView: true }), 350)
}

function errorText(err) {
  if (err.response?.status === 404) return 'The file is no longer on the server.'
  if (!err.response) return 'The server could not be reached.'
  return `Server error ${err.response.status}.`
}

async function loadField(field, { keepView = false } = {}) {
  const token = ++overviewToken
  loading.value = true
  loadError.value = null
  clearDetail()
  try {
    const res = await get2DImage(sessionId, field, pointSize.value)
    if (token !== overviewToken) return   // a newer request superseded this one
    const h = res.headers
    bounds.xmin = parseFloat(h['x-bounds-xmin'])
    bounds.xmax = parseFloat(h['x-bounds-xmax'])
    bounds.ymin = parseFloat(h['x-bounds-ymin'])
    bounds.ymax = parseFloat(h['x-bounds-ymax'])
    const newW = parseInt(h['x-image-width']  ?? '2048')
    const newH = parseInt(h['x-image-height'] ?? '2048')
    pointCount.value      = parseInt(h['x-point-count']       ?? '0')
    decimationRatio.value = parseFloat(h['x-decimation-ratio'] ?? '1')
    const img = await blobToImage(res.data)
    if (token !== overviewToken) { URL.revokeObjectURL(img.src); return }
    if (currentImage) URL.revokeObjectURL(currentImage.src)
    currentImage = img
    const sizeChanged = newW !== IMG_W || newH !== IMG_H
    IMG_W = newW; IMG_H = newH
    if (!keepView || sizeChanged) fitImage()
    draw()
    scheduleDetail(0)
  } catch (err) {
    if (token !== overviewToken) return
    console.error('Failed to load 2D image:', err)
    loadError.value = errorText(err)
  } finally {
    if (token === overviewToken) loading.value = false
  }
}

function blobToImage(blob) {
  return new Promise((resolve, reject) => {
    const img = new window.Image()
    img.onload = () => resolve(img)
    img.onerror = () => { URL.revokeObjectURL(img.src); reject(new Error('Image could not be decoded')) }
    img.src = URL.createObjectURL(blob)
  })
}

// ── Full-detail image of the visible area ────────────────────────────────────
function clearDetail() {
  clearTimeout(detailTimer)
  detailAbort?.abort()
  detailAbort = null
  refining.value = false
  if (detail.value) URL.revokeObjectURL(detail.value.img.src)
  detail.value = null
}

function scheduleDetail(delay = 250) {
  clearTimeout(detailTimer)
  detailTimer = setTimeout(requestDetail, delay)
}

async function requestDetail() {
  const canvas = canvasRef.value
  if (!canvas || !currentImage || loadError.value) return

  // Visible world rectangle, clipped to the file's extent
  const r   = canvas.getBoundingClientRect()
  const tl  = toWorld(r.left, r.top)
  const brw = toWorld(r.right, r.bottom)
  const view = {
    xmin: Math.max(bounds.xmin, tl.x),  xmax: Math.min(bounds.xmax, brw.x),
    ymin: Math.max(bounds.ymin, brw.y), ymax: Math.min(bounds.ymax, tl.y),
  }
  if (view.xmax <= view.xmin || view.ymax <= view.ymin) return   // panned off the data

  // Only worth it when zoomed in: overview pixels are magnified, or only part of the file is visible
  const fracX = (view.xmax - view.xmin) / (bounds.xmax - bounds.xmin)
  const fracY = (view.ymax - view.ymin) / (bounds.ymax - bounds.ymin)
  const zoomedIn = pan.scale > 1.1 || (decimationRatio.value < 0.995 && Math.max(fracX, fracY) < 0.9)
  if (!zoomedIn) {
    if (detail.value) { clearDetail(); draw() }
    return
  }

  // Render at the on-screen size of that rectangle (server accepts 256–4096 px per side)
  let w = (view.xmax - view.xmin) / (bounds.xmax - bounds.xmin) * IMG_W * pan.scale
  let h = (view.ymax - view.ymin) / (bounds.ymax - bounds.ymin) * IMG_H * pan.scale
  const up = Math.max(1, 256 / Math.min(w, h))
  const down = Math.min(1, 4096 / Math.max(w * up, h * up))
  w = Math.round(Math.min(4096, Math.max(256, w * up * down)))
  h = Math.round(Math.min(4096, Math.max(256, h * up * down)))

  detailAbort?.abort()
  const ctrl = new AbortController()
  detailAbort = ctrl
  refining.value = true
  try {
    const res = await get2DImage(sessionId, store.scalarField || 'elevation', pointSize.value, w, h, { view, signal: ctrl.signal })
    const img = await blobToImage(res.data)
    if (ctrl.signal.aborted) { URL.revokeObjectURL(img.src); return }
    if (detail.value) URL.revokeObjectURL(detail.value.img.src)
    detail.value = {
      img,
      bounds: view,
      pointCount: parseInt(res.headers['x-point-count'] ?? '0'),
      ratio: parseFloat(res.headers['x-decimation-ratio'] ?? '1'),
    }
    draw()
  } catch (err) {
    // Not critical: the overview is still shown
    if (err.name !== 'CanceledError' && err.name !== 'AbortError') console.warn('Detail render failed:', err)
  } finally {
    if (detailAbort === ctrl) { detailAbort = null; refining.value = false }
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
  clearTimeout(pointSizeTimer)
  overviewToken++
  clearDetail()
  if (currentImage) URL.revokeObjectURL(currentImage.src)
})

watch(() => store.scalarField, field => loadField(field, { keepView: true }))
watch(() => store.labeledRegions, () => draw(), { deep: true })

// ── Selection tools (assigned after mount) ───────────────────────────────────

const rectTool     = shallowRef(null)
const freehandTool = shallowRef(null)
const fixedTool    = shallowRef(null)

// ── Pan (middle mouse / Alt+left) ───────────────────────────────────────────

let isPanning = false, lastX = 0, lastY = 0

let didPan = false
function onMouseDown(e) {
  if (e.button === 1 || e.button === 2 || (e.button === 0 && (e.altKey || e.ctrlKey))) {
    isPanning = true; didPan = false; lastX = e.clientX; lastY = e.clientY; e.preventDefault()
  }
}
function onMouseMove(e) {
  if (!isPanning) return
  pan.offsetX += e.clientX - lastX
  pan.offsetY += e.clientY - lastY
  lastX = e.clientX; lastY = e.clientY
  didPan = true
  draw()
}
function endPan() {
  if (isPanning && didPan) scheduleDetail()
  isPanning = false
}
function onMouseUp()    { endPan() }
function onMouseLeave() { endPan() }

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
  scheduleDetail()
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
  if (e.button === 1 || e.button === 2 || (e.button === 0 && (e.altKey || e.ctrlKey))) return
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
.load-error {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  z-index: 30; text-align: center;
  background: #1a1a30; border: 1px solid #a44; border-radius: 10px;
  padding: 20px 28px; display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.load-error-title { color: #fcc; font-size: 15px; font-weight: 600; }
.load-error-detail { color: #aab; font-size: 13px; }
.load-error button {
  margin-top: 6px; background: #2a3a5a; border: 1px solid #445; color: #eee;
  padding: 5px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.load-error button:hover { background: #3a4a7a; }
.extract-error {
  position: absolute; bottom: 50px; left: 50%; transform: translateX(-50%);
  background: rgba(180,40,40,0.9); color: #fff; padding: 8px 18px;
  border-radius: 8px; font-size: 13px; cursor: pointer; z-index: 20;
  max-width: 80%; text-align: center;
}
</style>
