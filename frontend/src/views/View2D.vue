<template>
  <div class="view2d-layout" @click="dropdownOpen = false">
    <header class="toolbar">
      <!-- Load button — leftmost -->
      <button class="load-btn" @click.stop="fileInput.click()" :disabled="loadingFiles" title="Load one or more .las files">
        {{ loadingFiles ? `Uploading ${loadProgress}…` : '⬆ Load' }}
      </button>
      <input ref="fileInput" type="file" accept=".las,.LAS,.laz,.LAZ" multiple style="display:none" @change="onFilesSelected" />

      <!-- Split button -->
      <button class="split-btn" @click="splitModal = true" title="Split a large LAS/LAZ into tiles and download as ZIP">✂ Split</button>

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
        <button
          class="whole-btn"
          :disabled="extractingWhole"
          @click="loadWholePatch"
          title="Load the entire LAS file into the point cloud view"
        >{{ extractingWhole ? 'Loading…' : 'Whole Patch' }}</button>
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
          <span v-if="store.labelledPatchIds.has(region.patch_id)" class="labelled-badge" title="Labelled">C</span>
          <span class="patch-pts">{{ region.point_count.toLocaleString() }} pts</span>
        </div>
      </aside>
    </div>
  </div>

  <!-- Split modal -->
  <teleport to="body">
    <div v-if="splitModal" class="split-overlay" @click.self="splitModal = false">
      <div class="split-box">
        <h3>Split LAS / LAZ into tiles</h3>
        <div class="split-row">
          <label>File</label>
          <input type="file" accept=".las,.LAS,.laz,.LAZ" @change="onSplitFileSelected" />
        </div>
        <div class="split-row">
          <label>Tiles</label>
          <select v-model="splitNTiles">
            <option :value="4">4 tiles  (2 × 2)</option>
            <option :value="8">8 tiles  (2 × 4)</option>
            <option :value="16">16 tiles (4 × 4)</option>
            <option :value="32">32 tiles (4 × 8)</option>
          </select>
        </div>
        <p v-if="splitSelectedFile" class="split-filename">{{ splitSelectedFile.name }}</p>
        <p v-if="splitProgress" class="split-progress">Uploading… {{ splitProgress }}%</p>
        <div class="split-actions">
          <button @click="splitModal = false">Cancel</button>
          <button class="split-go" :disabled="!splitSelectedFile || splitting" @click="doSplit">
            {{ splitting ? 'Processing…' : 'Split & Download' }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session.js'
import { useView2DStore } from '../stores/view2d.js'
import { uploadFile, extractPatch, splitFile } from '../api/client.js'
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
const extractingWhole = ref(false)

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

async function loadWholePatch() {
  const sessionId = route.params.id
  const entry = session.sessions.find(s => s.sessionId === sessionId)
  if (!entry?.bounds) return
  extractingWhole.value = true
  try {
    const bounds = entry.bounds
    const res = await extractPatch(sessionId, {
      selection_type: 'rectangle',
      bounds_2d: {
        x_min: bounds.x[0],
        x_max: bounds.x[1],
        y_min: bounds.y[0],
        y_max: bounds.y[1],
      },
    })
    const { patch_id, patch_number } = res.data
    router.push(`/session/${sessionId}/patch/${patch_id}?n=${patch_number}&whole=1`)
  } catch (err) {
    console.error('Whole patch extraction failed:', err)
  } finally {
    extractingWhole.value = false
  }
}

// --- Split feature ---
const splitModal = ref(false)
const splitNTiles = ref(4)
const splitSelectedFile = ref(null)
const splitting = ref(false)
const splitProgress = ref(0)

function onSplitFileSelected(e) {
  splitSelectedFile.value = e.target.files[0] || null
}

async function doSplit() {
  if (!splitSelectedFile.value || splitting.value) return
  splitting.value = true
  splitProgress.value = 0
  try {
    const res = await splitFile(splitSelectedFile.value, splitNTiles.value, pct => { splitProgress.value = pct })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = splitSelectedFile.value.name.replace(/\.[^.]+$/, '') + '.zip'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    splitModal.value = false
    splitSelectedFile.value = null
  } catch (err) {
    alert('Split failed: ' + (err.message || 'unknown error'))
  } finally {
    splitting.value = false
    splitProgress.value = 0
  }
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
  gap: 10px;
  padding: 8px 16px;
  background: #0d0d1f;
  border-bottom: 1px solid #334;
  flex-shrink: 0;
}
.tool-group { display: flex; gap: 6px; margin-left: auto; }
.whole-btn {
  background: #2a3a5e;
  border-color: #4a6aae;
  color: #adf;
}
.whole-btn:hover:not(:disabled) { background: #3a4a7e; }
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
.labelled-badge { color: #4f4; font-size: 10px; font-weight: 700; margin-right: 4px; flex-shrink: 0; }
.patch-pts { color: #778; }

.split-btn {
  background: #2a3a3e;
  border-color: #4a8a8e;
  color: #aef;
}
.split-btn:hover { background: #3a4a5e; }

/* Modal overlay */
.split-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.65);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.split-box {
  background: #12122a;
  border: 1px solid #335;
  border-radius: 10px;
  padding: 28px 32px;
  min-width: 360px;
  display: flex; flex-direction: column; gap: 16px;
}
.split-box h3 { margin: 0; color: #adf; font-size: 1.1rem; }
.split-row { display: flex; align-items: center; gap: 12px; }
.split-row label { width: 44px; color: #889; font-size: 13px; }
.split-row select, .split-row input[type=file] {
  flex: 1; background: #1a1a3a; border: 1px solid #445;
  color: #cce; border-radius: 6px; padding: 5px 8px; font-size: 13px;
}
.split-filename { margin: 0; font-size: 12px; color: #77a; }
.split-progress { margin: 0; font-size: 12px; color: #7af; }
.split-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 4px; }
.split-go { background: #2a5a3e; border-color: #4a9a6e; color: #afa; }
.split-go:hover:not(:disabled) { background: #3a6a4e; }
</style>
