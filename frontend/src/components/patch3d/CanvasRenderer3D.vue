<template>
  <div ref="container" class="canvas3d">
    <div v-if="loading" class="loading">Loading patch...</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { useThreeScene } from '../../composables/useThreeScene.js'
import { usePointCloud3D } from '../../composables/usePointCloud3D.js'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useRoute } from 'vue-router'

const container = ref(null)
const route = useRoute()
const store = usePatch3DStore()

const { scene, camera, renderer } = useThreeScene(container, 'perspective')
const { load, loading, pointCount, highlightIndices, applyLabelColor, resetColors, getPositions, dispose } = usePointCloud3D(scene, route.params.id, route.params.patchId)

let controls = null

onMounted(async () => {
  const result = await load()
  store.pointCount = pointCount.value
  if (result?.center && camera.value) {
    const { center, positions } = result
    // Compute bounding box extents from positions to set proportional camera offset
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
    controls.update()
  }
})

onBeforeUnmount(() => {
  controls?.dispose()
  dispose()
})

// Expose for parent (lasso integration in Task 10)
defineExpose({ highlightIndices, applyLabelColor, resetColors, getPositions, camera, renderer })
</script>

<style scoped>
.canvas3d { position: relative; width: 100%; height: 100%; }
.loading { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); color: #adf; font-size: 1.2rem; }
</style>
