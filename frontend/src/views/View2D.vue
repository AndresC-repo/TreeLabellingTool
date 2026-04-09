<template>
  <div class="view2d-layout">
    <header class="toolbar">
      <span class="title">{{ session.filename ?? 'Point Cloud' }}</span>
      <ScalarSelector />
      <div class="tool-group">
        <button
          v-for="tool in tools"
          :key="tool.id"
          :class="{ active: store.activeTool === tool.id }"
          @click="store.activeTool = tool.id"
        >{{ tool.label }}</button>
      </div>
      <button class="load-btn" @click="router.push('/')">&#8593; Load new point cloud</button>
    </header>
    <div class="main-area">
      <CanvasRenderer2D class="canvas-area" />
      <aside v-if="store.labeledRegions.length > 0" class="side-panel">
        <h3>Labeled Regions</h3>
        <div
          v-for="region in store.labeledRegions"
          :key="region.patch_id"
          class="region-item"
          @click="openPatch(region)"
        >
          <button class="remove-btn" @click.stop="store.removeRegion(region.patch_id)" title="Remove region">&#x2715;</button>
          <span class="patch-id">patch_{{ region.patch_number }}</span>
          <span class="patch-pts">{{ region.point_count.toLocaleString() }} pts</span>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session.js'
import { useView2DStore } from '../stores/view2d.js'
import CanvasRenderer2D from '../components/view2d/CanvasRenderer2D.vue'
import ScalarSelector from '../components/view2d/ScalarSelector.vue'

const route  = useRoute()
const router = useRouter()
const session = useSessionStore()
const store  = useView2DStore()

const tools = [
  { id: 'rectangle', label: 'Rectangle' },
  { id: 'freehand',  label: 'Freehand'  },
  { id: 'fixed',     label: 'Fixed Rect' },
]

function openPatch(region) {
  router.push(`/session/${route.params.id}/patch/${region.patch_id}?n=${region.patch_number}`)
}
</script>

<style scoped>
.view2d-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  background: #0d0d1f;
  border-bottom: 1px solid #334;
  flex-shrink: 0;
}
.title { font-weight: 600; color: #adf; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-group { display: flex; gap: 6px; }
button {
  background: #2a2a4e;
  color: #cce;
  border: 1px solid #445;
  padding: 5px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
}
button:hover { background: #3a3a6e; }
button.active { background: #3a5a8e; border-color: #7ab3ff; color: #fff; }
.main-area { display: flex; flex: 1; overflow: hidden; }
.canvas-area { flex: 1; }
.side-panel {
  width: 220px;
  background: #0d0d1f;
  border-left: 1px solid #334;
  padding: 16px;
  overflow-y: auto;
  flex-shrink: 0;
}
h3 { color: #adf; font-size: 13px; font-weight: 600; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
.region-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  border: 1px solid transparent;
  margin-bottom: 4px;
  transition: background 0.1s;
}
.region-item:hover { background: #2a2a4e; border-color: #445; }
.remove-btn {
  background: none; border: none; color: #556; cursor: pointer;
  font-size: 12px; padding: 0 4px; line-height: 1; flex-shrink: 0;
}
.remove-btn:hover { color: #f66; }
.patch-id { color: #aac; font-family: monospace; flex: 1; }
.patch-pts { color: #778; }
.load-btn {
  background: #1a3a2a; color: #6db; border: 1px solid #2a5a3a;
  padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
  white-space: nowrap;
}
.load-btn:hover { background: #2a4a3a; }
</style>
