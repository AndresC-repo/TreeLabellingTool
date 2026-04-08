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
    const { center } = result
    // Position camera to look at patch from above/side
    camera.value.position.set(center.x, center.y - 50, center.z + 50)
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
