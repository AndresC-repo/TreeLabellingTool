<template>
  <canvas
    ref="canvas"
    class="lasso-canvas"
    :style="{ pointerEvents: rotateMode ? 'none' : 'all' }"
    @click="onLeftClick"
    @mousemove="onMove"
    @contextmenu.prevent="onFinish"
    @keydown.esc.prevent="onCancel"
    tabindex="0"
  ></canvas>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  drawing: Boolean,
  lassoPoints: Array,
  processing: Boolean,
  rotateMode: Boolean,
})
const emit = defineEmits(['addVertex', 'previewMove', 'finish', 'cancel'])

const canvas = ref(null)
let ctx = null

onMounted(() => {
  const c = canvas.value
  ctx = c.getContext('2d')
  syncSize()
  const ro = new ResizeObserver(syncSize)
  ro.observe(c)
  onBeforeUnmount(() => ro.disconnect())
})

function syncSize() {
  const c = canvas.value
  if (!c) return
  c.width = c.offsetWidth
  c.height = c.offsetHeight
}

const previewPoint = ref(null)

function redraw() {
  if (!ctx || !canvas.value) return
  ctx.clearRect(0, 0, canvas.value.width, canvas.value.height)
  const pts = props.lassoPoints
  if (!pts || pts.length === 0) return

  ctx.strokeStyle = '#00ff44'
  ctx.lineWidth = 2

  // Filled polygon (confirmed vertices)
  ctx.beginPath()
  ctx.moveTo(pts[0].x, pts[0].y)
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y)
  if (pts.length > 2) {
    ctx.fillStyle = 'rgba(0, 255, 68, 0.08)'
    ctx.fill()
  }
  ctx.setLineDash([])
  ctx.stroke()

  // Draw vertex dots
  ctx.fillStyle = '#00ff44'
  for (const p of pts) {
    ctx.beginPath()
    ctx.arc(p.x, p.y, 3, 0, Math.PI * 2)
    ctx.fill()
  }

  // Preview line from last vertex to cursor
  if (previewPoint.value && props.drawing) {
    const last = pts[pts.length - 1]
    ctx.beginPath()
    ctx.moveTo(last.x, last.y)
    ctx.lineTo(previewPoint.value.x, previewPoint.value.y)
    ctx.setLineDash([4, 4])
    ctx.strokeStyle = 'rgba(0, 255, 68, 0.5)'
    ctx.stroke()
    ctx.setLineDash([])
  }
}

watch(() => props.lassoPoints, redraw, { deep: true })
watch(previewPoint, redraw, { deep: true })

function onLeftClick(e) { if (e.button === 0) emit('addVertex', e) }
function onMove(e) { previewPoint.value = { x: e.offsetX, y: e.offsetY }; emit('previewMove', e) }
function onFinish(e) { previewPoint.value = null; emit('finish', e) }
function onCancel(e) { previewPoint.value = null; emit('cancel', e) }
</script>

<style scoped>
.lasso-canvas {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  cursor: crosshair;
  outline: none;
  pointer-events: all;
}
</style>
