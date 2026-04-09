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
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { useThreeScene } from '../../composables/useThreeScene.js'
import { usePointCloud3D } from '../../composables/usePointCloud3D.js'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useRoute } from 'vue-router'
import { useLasso3D } from '../../composables/useLasso3D.js'
import LassoOverlay from './LassoOverlay.vue'

const container = ref(null)
const route = useRoute()
const store = usePatch3DStore()

const { scene, camera, renderer } = useThreeScene(container, 'perspective')
const pc3d = usePointCloud3D(scene, route.params.id, route.params.patchId)
const { load, loading, pointCount, highlightIndices, applyLabelColor, resetColors, setViewMode, getPositions, dispose } = pc3d

const lasso = useLasso3D(camera, renderer)

let controls = null
const rotateMode = ref(true)

function setRotate(val) {
  rotateMode.value = val
  if (controls) controls.enabled = val
  if (val) lasso.cancelLasso()
}

// React to store viewMode changes (from buttons here or from LabelPanel)
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

onMounted(async () => {
  const result = await load()
  store.pointCount = pointCount.value
  if (result?.center && camera.value) {
    const { center, positions } = result
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, minZ = Infinity, maxZ = -Infinity
    for (let i = 0; i < positions.length; i += 3) {
      if (positions[i]   < minX) minX = positions[i];   if (positions[i]   > maxX) maxX = positions[i]
      if (positions[i+1] < minY) minY = positions[i+1]; if (positions[i+1] > maxY) maxY = positions[i+1]
      if (positions[i+2] < minZ) minZ = positions[i+2]; if (positions[i+2] > maxZ) maxZ = positions[i+2]
    }
    const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 1)
    const dist = span * 1.5
    camera.value.position.set(center.x, center.y - dist, center.z + dist)
    camera.value.lookAt(center.x, center.y, center.z)
    controls = new OrbitControls(camera.value, renderer.value.domElement)
    controls.target.set(center.x, center.y, center.z)
    controls.enabled = rotateMode.value
    controls.update()
  }
})

onBeforeUnmount(() => {
  controls?.dispose()
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
</style>
