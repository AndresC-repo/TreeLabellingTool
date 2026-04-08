<template>
  <canvas
    ref="canvas"
    class="lasso-canvas"
    @mousedown="onDown"
    @mousemove="onMove"
    @dblclick="onFinish"
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
})
const emit = defineEmits(['start', 'addPoint', 'finish', 'cancel'])

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

watch(() => props.lassoPoints, () => {
  if (!ctx || !canvas.value) return
  ctx.clearRect(0, 0, canvas.value.width, canvas.value.height)
  const pts = props.lassoPoints
  if (!pts || pts.length === 0) return
  ctx.beginPath()
  ctx.moveTo(pts[0].x, pts[0].y)
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y)
  if (!props.drawing) ctx.closePath()
  ctx.strokeStyle = '#ffff00'
  ctx.lineWidth = 2
  ctx.setLineDash(props.drawing ? [] : [4, 4])
  ctx.stroke()
  // Fill semi-transparent if drawing
  if (props.drawing && pts.length > 2) {
    ctx.fillStyle = 'rgba(255, 255, 0, 0.08)'
    ctx.fill()
  }
}, { deep: true })

function onDown(e) { emit('start', e) }
function onMove(e) { emit('addPoint', e) }
function onFinish(e) { emit('finish', e) }
function onCancel(e) { emit('cancel', e) }
</script>

<style scoped>
.lasso-canvas {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  cursor: crosshair;
  outline: none;
}
</style>
