<template>
  <div class="patch-layout">
    <header class="toolbar">
      <router-link :to="`/session/${$route.params.id}/view`">← Back to 2D View</router-link>
      <span class="patch-label">patch_{{ store.patchNumber }}</span>
      <span class="point-count" v-if="store.pointCount > 0">{{ store.pointCount.toLocaleString() }} points</span>
    </header>
    <div class="main">
      <CanvasRenderer3D ref="renderer3d" class="canvas" />
      <aside class="side-panel">
        <LabelPanel ref="labelPanel" />
        <PatchLegend v-if="store.viewMode === 'classification'" />
        <InferenceLegend
          v-if="store.viewMode === 'prediction' || store.viewMode === 'inference-chm'"
          @segment-done="onSegmentDone"
        />
        <SavePanel ref="savePanel" />
      </aside>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import { usePatch3DStore } from '../stores/patch3d.js'
import CanvasRenderer3D from '../components/patch3d/CanvasRenderer3D.vue'
import LabelPanel from '../components/patch3d/LabelPanel.vue'
import PatchLegend from '../components/patch3d/PatchLegend.vue'
import InferenceLegend from '../components/patch3d/InferenceLegend.vue'
import SavePanel from '../components/patch3d/SavePanel.vue'

const route = useRoute()
const store = usePatch3DStore()
const renderer3d = ref(null)
const labelPanel = ref(null)
const savePanel = ref(null)

function onSegmentDone(newLabels) {
  // applyPredictionColors recomputes both prediction and inference-CHM color buffers
  renderer3d.value?.applyPredictionColors(newLabels)
  // Stay in whichever inference sub-view was active (prediction or inference-chm)
  if (store.viewMode !== 'inference-chm') store.viewMode = 'prediction'
}

function onKeyDown(e) {
  // Ignore shortcuts when typing in an input/textarea
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return

  // Ctrl+S / Cmd+S — check before switch so plain 'S' still works
  if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
    e.preventDefault()
    savePanel.value?.save()
    return
  }

  switch (e.key) {
    case 'r':
    case 'R':
      renderer3d.value?.toggleRotate()
      break
    case 's':
    case 'S':
      renderer3d.value?.setSideView()
      break
    case 't':
    case 'T':
      renderer3d.value?.setTopView()
      break
    case 'v':
    case 'V': {
      // In inference mode cycle through inference sub-views; otherwise standard terrain views
      const inferenceModes = ['prediction', 'dtm', 'inference-chm']
      const standardModes  = ['elevation',  'dtm', 'chm']
      const isInferenceMode = inferenceModes.includes(store.viewMode)
      const modes = (isInferenceMode && store.hasPrediction) ? inferenceModes : standardModes
      const cur = modes.indexOf(store.viewMode)
      store.viewMode = modes[(cur < 0 ? 0 : cur + 1) % modes.length]
      break
    }
    case 'l':
    case 'L':
      store.viewMode = 'classification'
      break
    case 'i':
    case 'I':
      renderer3d.value?.runPrediction('v1')
      break
    case 'Enter':
    case ' ':
      e.preventDefault()
      labelPanel.value?.applyLabel()
      break
    case 'g':
    case 'G':
      labelPanel.value?.applyGnd()
      break
  }
}

onMounted(() => {
  store.patchNumber = parseInt(route.query.n) || 1
  document.addEventListener('keydown', onKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeyDown)
  store.reset()
})
</script>

<style scoped>
.patch-layout { display: flex; flex-direction: column; height: 100vh; }
.toolbar { display: flex; align-items: center; gap: 16px; padding: 8px 16px; background: #0d0d1f; border-bottom: 1px solid #334; flex-shrink: 0; }
a { color: #7af; text-decoration: none; font-size: 14px; }
.patch-label { font-weight: bold; color: #eee; font-family: monospace; }
.point-count { font-size: 13px; color: #88a; margin-left: auto; }
.main { display: flex; flex: 1; overflow: hidden; }
.canvas { flex: 1; }
.side-panel { width: 260px; background: #0d0d1f; border-left: 1px solid #334; padding: 16px; display: flex; flex-direction: column; gap: 24px; overflow-y: auto; }
</style>
