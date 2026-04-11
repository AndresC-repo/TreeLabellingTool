<template>
  <div class="view2d-layout" @click="dropdownOpen = false">
    <header class="toolbar">
      <!-- Load button — leftmost -->
      <button class="load-btn" @click.stop="fileInput.click()" :disabled="loadingFiles" title="Load one or more .las files">
        {{ loadingFiles ? `Uploading ${loadProgress}…` : '⬆ Load' }}
      </button>
      <input ref="fileInput" type="file" accept=".las,.LAS,.laz,.LAZ" multiple style="display:none" @change="onFilesSelected" />

      <!-- File dropdown -->
      <div class="file-dropdown" @click.stop>
        <button class="file-trigger" @click="dropdownOpen = !dropdownOpen" :title="currentFilename">
          <span class="trigger-name">{{ currentFilename }}</span>
          <span class="trigger-arrow">{{ dropdownOpen ? '▲' : '▼' }}</span>
        </button>
        <div v-if="dropdownOpen" class="dropdown-panel">
          <div
            v-for="s in session.sessions"
            :key="s.sessionId"
            class="dropdown-item"
            :class="{ active: s.sessionId === route.params.id }"
          >
            <span class="item-name" @click="switchSession(s)" :title="s.filename">{{ s.filename }}</span>
            <button class="item-remove" @click.stop="removeSession(s.sessionId)" title="Remove file">&#x2715;</button>
          </div>
        </div>
      </div>

      <ScalarSelector />
      <div class="tool-group">
        <button
          v-for="tool in tools"
          :key="tool.id"
          :class="{ active: store.activeTool === tool.id }"
          @click="store.activeTool = tool.id"
        >{{ tool.label }}</button>
      </div>
    </header>
    <div class="main-area">
      <ClassificationLegend v-if="store.scalarField === 'classification'" />
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
import { ref, computed, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session.js'
import { useView2DStore } from '../stores/view2d.js'
import { uploadFile } from '../api/client.js'
import CanvasRenderer2D from '../components/view2d/CanvasRenderer2D.vue'
import ScalarSelector from '../components/view2d/ScalarSelector.vue'
import ClassificationLegend from '../components/view2d/ClassificationLegend.vue'

const route  = useRoute()
const router = useRouter()
const session = useSessionStore()
const store  = useView2DStore()

const fileInput = ref(null)
const loadingFiles = ref(false)
const loadProgress = ref('')
const dropdownOpen = ref(false)

const currentFilename = computed(() =>
  session.sessions.find(s => s.sessionId === route.params.id)?.filename ?? session.filename ?? 'Point Cloud'
)

const tools = [
  { id: 'rectangle', label: 'Rectangle' },
  { id: 'freehand',  label: 'Freehand'  },
  { id: 'fixed',     label: 'Fixed Rect' },
]

async function onFilesSelected(e) {
  const files = Array.from(e.target.files)
  e.target.value = ''
  if (!files.length) return

  loadingFiles.value = true
  const errors = []

  for (let i = 0; i < files.length; i++) {
    loadProgress.value = `${i + 1}/${files.length}`
    try {
      const res = await uploadFile(files[i])
      session.addSession(res.data)
    } catch (err) {
      errors.push(files[i].name)
    }
  }

  loadingFiles.value = false
  loadProgress.value = ''
  if (errors.length) alert(`Failed to upload: ${errors.join(', ')}`)
}

function switchSession(entry) {
  dropdownOpen.value = false
  if (entry.sessionId === route.params.id) return
  store.reset()
  session.switchTo(entry)
  router.push(`/session/${entry.sessionId}/view`)
}

function removeSession(id) {
  const wasActive = id === route.params.id
  session.removeSession(id)
  dropdownOpen.value = false
  if (wasActive && session.sessionId) {
    store.reset()
    router.push(`/session/${session.sessionId}/view`)
  }
}

function openPatch(region) {
  router.push(`/session/${route.params.id}/patch/${region.patch_id}?n=${region.patch_number}`)
}

onBeforeUnmount(() => store.reset())
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
  gap: 10px;
  padding: 8px 16px;
  background: #0d0d1f;
  border-bottom: 1px solid #334;
  flex-shrink: 0;
}
.tool-group { display: flex; gap: 6px; margin-left: auto; }
button {
  background: #2a2a4e;
  color: #cce;
  border: 1px solid #445;
  padding: 5px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s;
  white-space: nowrap;
}
button:hover:not(:disabled) { background: #3a3a6e; }
button.active { background: #3a5a8e; border-color: #7ab3ff; color: #fff; }
button:disabled { opacity: 0.6; cursor: default; }
.load-btn {
  background: #1a3a2a; color: #6db; border: 1px solid #2a5a3a;
  flex-shrink: 0;
}
.load-btn:hover:not(:disabled) { background: #2a4a3a; }

/* File dropdown */
.file-dropdown { position: relative; }
.file-trigger {
  display: flex; align-items: center; gap: 8px;
  max-width: 240px; min-width: 120px;
  background: #2a2a4e; color: #adf;
  border: 1px solid #445; padding: 5px 10px;
  border-radius: 6px; cursor: pointer; font-size: 13px;
}
.file-trigger:hover { background: #333360; }
.trigger-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; text-align: left; }
.trigger-arrow { font-size: 9px; color: #778; flex-shrink: 0; }
.dropdown-panel {
  position: absolute; top: calc(100% + 4px); left: 0;
  min-width: 260px; max-width: 360px;
  background: #1a1a30; border: 1px solid #445;
  border-radius: 8px; z-index: 100;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  overflow: hidden;
}
.dropdown-item {
  display: flex; align-items: center;
  padding: 8px 10px 8px 14px;
  border-bottom: 1px solid #2a2a44;
  transition: background 0.1s;
}
.dropdown-item:last-child { border-bottom: none; }
.dropdown-item.active { background: #1e3a5a; }
.dropdown-item:hover { background: #252545; }
.dropdown-item.active:hover { background: #244060; }
.item-name {
  flex: 1; font-size: 13px; color: #cce;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  cursor: pointer;
}
.dropdown-item.active .item-name { color: #adf; font-weight: 600; }
.item-remove {
  background: none; border: none; color: #556; cursor: pointer;
  font-size: 11px; padding: 2px 4px; line-height: 1; flex-shrink: 0;
  border-radius: 3px;
}
.item-remove:hover { color: #f66; background: rgba(255,80,80,0.1); }

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
  align-items: center;
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
.patch-id { color: #aac; font-family: monospace; flex: 1; padding: 0 6px; }
.patch-pts { color: #778; }
</style>
