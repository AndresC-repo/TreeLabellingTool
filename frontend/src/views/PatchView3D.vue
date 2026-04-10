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
import SavePanel from '../components/patch3d/SavePanel.vue'

const route = useRoute()
const store = usePatch3DStore()
const renderer3d = ref(null)
const labelPanel = ref(null)
const savePanel = ref(null)

function onKeyDown(e) {
  // Ignore shortcuts when typing in an input/textarea
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return

  switch (e.key) {
    case 'r':
    case 'R':
      renderer3d.value?.setRotate(true)
      break
    case 's':
    case 'S':
      if (!e.ctrlKey && !e.metaKey) renderer3d.value?.setRotate(false)
      break
    case 'v':
    case 'V':
      store.viewMode = store.viewMode === 'elevation' ? 'classification' : 'elevation'
      break
    case 'Enter':
      e.preventDefault()
      labelPanel.value?.applyLabel()
      break
    case 'g':
    case 'G':
      labelPanel.value?.applyGnd()
      break
  }
  // Ctrl+S / Cmd+S — must check after switch to avoid conflict with plain 'S'
  if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
    e.preventDefault()
    savePanel.value?.save()
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
