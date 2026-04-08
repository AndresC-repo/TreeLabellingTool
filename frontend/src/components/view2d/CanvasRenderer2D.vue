<template>
  <div ref="containerRef" class="canvas-container">
    <div v-if="loading" class="overlay-msg">Loading point cloud…</div>
    <div class="info-badge" v-if="pointCount > 0">
      {{ pointCount.toLocaleString() }} pts
      <span v-if="decimationRatio < 0.995" class="dim">
        ({{ Math.round(decimationRatio * 100) }}% of file)
      </span>
    </div>
    <!-- SVG overlay for selection drawing — added in Task 8 -->
    <svg class="svg-overlay" ref="svgRef"></svg>
    <!-- Canvas overlay for labeled region hatching — added in Task 8 -->
    <canvas ref="hatchRef" class="hatch-overlay"></canvas>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useThreeScene } from '../../composables/useThreeScene.js'
import { usePointCloud2D } from '../../composables/usePointCloud2D.js'
import { useView2DStore } from '../../stores/view2d.js'

const route = useRoute()
const sessionId = route.params.id
const containerRef = ref(null)
const svgRef = ref(null)
const hatchRef = ref(null)
const loading = ref(false)
const pointCount = ref(0)
const decimationRatio = ref(1)

const { scene, camera, renderer } = useThreeScene(containerRef, 'orthographic')
const { load, loading: pc2dLoading, pointCount: pc2dCount, decimationRatio: pc2dRatio } = usePointCloud2D(scene, sessionId)
const store = useView2DStore()

watch(pc2dLoading, v => { loading.value = v })
watch(pc2dCount, v => { pointCount.value = v })
watch(pc2dRatio, v => { decimationRatio.value = v })

onMounted(async () => {
  const center = await load('classification')
  if (center && camera.value) {
    camera.value.position.set(center.x, center.y, 100)
    camera.value.lookAt(center.x, center.y, 0)
  }

  const el = containerRef.value
  el.addEventListener('mousedown', startPan)
  el.addEventListener('mousemove', doPan)
  el.addEventListener('mouseup', endPan)
  el.addEventListener('mouseleave', endPan)
  el.addEventListener('wheel', onWheel, { passive: false })
})

watch(() => store.scalarField, async field => {
  const center = await load(field)
  if (center && camera.value) {
    camera.value.position.set(center.x, center.y, 100)
    camera.value.lookAt(center.x, center.y, 0)
  }
})

// Pan (middle mouse / Alt+drag)
let isPanning = false, lastX = 0, lastY = 0

function startPan(e) {
  if (e.button === 1 || (e.button === 0 && e.altKey)) {
    isPanning = true
    lastX = e.clientX; lastY = e.clientY
    e.preventDefault()
  }
}
function doPan(e) {
  if (!isPanning || !camera.value) return
  const dx = e.clientX - lastX
  const dy = e.clientY - lastY
  camera.value.position.x -= dx / camera.value.zoom
  camera.value.position.y += dy / camera.value.zoom
  lastX = e.clientX; lastY = e.clientY
}
function endPan() { isPanning = false }

function onWheel(e) {
  if (!camera.value) return
  e.preventDefault()
  const factor = e.deltaY > 0 ? 1 / 1.1 : 1.1
  camera.value.zoom = Math.max(0.001, camera.value.zoom * factor)
  camera.value.updateProjectionMatrix()
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
.svg-overlay, .hatch-overlay {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  pointer-events: none;
}
</style>
