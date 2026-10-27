<template>
  <div
    class="view2d-layout"
    @click="dropdownOpen = false"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <header class="toolbar">
      <!-- Load button — leftmost -->
      <button class="load-btn" @click.stop="fileInput.click()" :disabled="loadingFiles" :title="loadingFiles ? uploadingName : 'Load one or more .las/.laz files (or drop them anywhere)'">
        {{ loadingFiles ? loadProgress : '⬆ Load' }}
      </button>
      <input ref="fileInput" type="file" accept=".las,.LAS,.laz,.LAZ" multiple style="display:none" @change="onFilesSelected" />

      <!-- Split button -->
      <button class="split-btn" @click="splitModal = true" title="Split a large LAS/LAZ into tiles and download as ZIP">✂ Split</button>
      <router-link to="/dataset" class="dataset-btn" title="What has been labelled: tiles, patches, trees per region">📊 Dataset</router-link>

      <!-- File dropdown -->
      <div class="file-dropdown" @click.stop>
        <button class="file-trigger" @click="dropdownOpen = !dropdownOpen" :title="currentFilename">
          <span class="trigger-name">{{ currentFilename }}</span>
          <span class="trigger-arrow">{{ dropdownOpen ? '▲' : '▼' }}</span>
        </button>
        <div v-if="dropdownOpen && session.sessions.length" class="dropdown-panel">
          <div class="dropdown-head">
            <label class="select-all" :title="allSelected ? 'Clear selection' : 'Select all files'">
              <input
                type="checkbox"
                :checked="allSelected"
                :indeterminate.prop="someSelected && !allSelected"
                @change="toggleAll"
              />
              <span>{{ selectedIds.size ? `${selectedIds.size} selected` : `${session.sessions.length} file${session.sessions.length === 1 ? '' : 's'}` }}</span>
            </label>
            <button
              v-if="selectedIds.size"
              class="bulk-delete"
              :disabled="removing"
              @click="requestRemove(selectedEntries)"
            >Delete selected ({{ selectedIds.size }})</button>
          </div>
          <div class="dropdown-list">
            <div
              v-for="s in session.sessions"
              :key="s.sessionId"
              class="dropdown-item"
              :class="{ active: s.sessionId === route.params.id, selected: selectedIds.has(s.sessionId) }"
            >
              <input
                type="checkbox"
                class="item-check"
                :checked="selectedIds.has(s.sessionId)"
                @click="onCheckClick(s, $event)"
                title="Select (Shift+click for a range)"
              />
              <span class="item-name" @click="switchSession(s)" :title="s.filename">{{ s.filename }}</span>
              <button class="item-remove" @click.stop="requestRemove([s])" :disabled="removing" title="Delete file">&#x2715;</button>
            </div>
          </div>
        </div>
      </div>

      <ScalarSelector v-if="hasActive" />
      <div class="tool-group">
        <button
          v-for="tool in tools"
          :key="tool.id"
          :class="{ active: store.activeTool === tool.id }"
          :disabled="!hasActive"
          @click="store.activeTool = tool.id"
        >{{ tool.label }}</button>
        <button
          class="whole-btn"
          :disabled="extractingWhole || !hasActive"
          @click="loadWholePatch"
          title="Load the entire LAS file into the point cloud view"
        >{{ extractingWhole ? 'Loading…' : 'Whole Patch' }}</button>
      </div>
      <HelpButton page="view2d" />
    </header>
    <div v-if="!ready" class="empty-state">
      <p class="empty-hint">Loading…</p>
    </div>
    <div v-else-if="!hasActive" class="empty-state">
      <p class="empty-title">{{ session.sessions.length ? 'No point cloud open' : 'No point cloud loaded' }}</p>
      <p class="empty-hint">
        {{ session.sessions.length ? 'Pick a file from the list above, or load a new one.' : 'Load a .las / .laz file to start labelling.' }}
      </p>
      <button class="load-btn" @click.stop="fileInput.click()" :disabled="loadingFiles">
        {{ loadingFiles ? loadProgress : '⬆ Load point cloud' }}
      </button>
      <p class="empty-drop">or drop files anywhere in this window</p>
    </div>
    <div v-else class="main-area">
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
          <button class="remove-btn" @click.stop="requestRemoveRegion(region)" :disabled="removingRegion === region.patch_id" title="Delete patch">&#x2715;</button>
          <span class="patch-id">patch_{{ region.patch_number }}</span>
          <span v-if="store.labelledPatchIds.has(region.patch_id)" class="labelled-badge" title="Labelled">C</span>
          <span class="patch-pts">{{ region.point_count.toLocaleString() }} pts</span>
        </div>
      </aside>
    </div>

    <div v-if="dragActive" class="drop-overlay">
      <p>Drop .las / .laz files to load</p>
    </div>
  </div>

  <!-- Delete confirmation -->
  <teleport to="body">
    <div v-if="pendingRemove" class="split-overlay" @click.self="pendingRemove = null">
      <div class="split-box">
        <h3>
          Delete {{ pendingRemove.entries.length === 1 ? pendingRemove.entries[0].filename : `${pendingRemove.entries.length} files` }}?
        </h3>
        <p class="confirm-text">
          <template v-if="pendingRemove.entries.length === 1">
            This file has <strong>{{ pendingRemove.patchCount }}</strong>
            {{ pendingRemove.patchCount === 1 ? 'patch' : 'patches' }} on the server.
          </template>
          <template v-else>
            Together they have <strong>{{ pendingRemove.patchCount }}</strong>
            {{ pendingRemove.patchCount === 1 ? 'patch' : 'patches' }} on the server.
          </template>
          Deleting removes the files, their patches and any saved outputs you haven't downloaded.
          Training examples are kept.
        </p>
        <ul v-if="pendingRemove.entries.length > 1" class="confirm-list">
          <li v-for="e in pendingRemove.entries" :key="e.sessionId">
            {{ e.filename }}<span v-if="pendingRemove.counts[e.sessionId]" class="confirm-count"> · {{ pendingRemove.counts[e.sessionId] }} patch{{ pendingRemove.counts[e.sessionId] === 1 ? '' : 'es' }}</span>
          </li>
        </ul>
        <div class="split-actions">
          <button @click="pendingRemove = null">Cancel</button>
          <button class="danger-btn" @click="confirmRemove">Delete</button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- Patch delete confirmation (only for labelled patches) -->
  <teleport to="body">
    <div v-if="pendingRegion" class="split-overlay" @click.self="pendingRegion = null">
      <div class="split-box">
        <h3>Delete patch_{{ pendingRegion.patch_number }}?</h3>
        <p class="confirm-text">
          This patch has labels. Deleting removes the patch and any saved output you haven't downloaded.
          Training examples are kept.
        </p>
        <div class="split-actions">
          <button @click="pendingRegion = null">Cancel</button>
          <button class="danger-btn" @click="removeRegion(pendingRegion)">Delete</button>
        </div>
      </div>
    </div>
  </teleport>

  <!-- Split modal -->
  <teleport to="body">
    <div v-if="splitModal" class="split-overlay" @click.self="splitStage === 'idle' && (splitModal = false)">
      <div class="split-box">
        <h3>Split LAS / LAZ into tiles</h3>

        <!-- Stage: idle — pick file + tile count -->
        <template v-if="splitStage === 'idle'">
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
          <p v-if="splitSelectedFile" class="split-filename">📄 {{ splitSelectedFile.name }}</p>
          <div class="split-actions">
            <button @click="splitModal = false">Cancel</button>
            <button class="split-go" :disabled="!splitSelectedFile" @click="doSplit">Upload & Split</button>
          </div>
        </template>

        <!-- Stage: uploading -->
        <template v-else-if="splitStage === 'uploading'">
          <p class="split-status">⬆ Uploading file…</p>
          <div class="split-progress-bar">
            <div class="split-progress-fill" :style="{ width: splitUploadPct + '%' }"></div>
          </div>
          <p class="split-pct">{{ splitUploadPct }}%</p>
        </template>

        <!-- Stage: splitting -->
        <template v-else-if="splitStage === 'splitting'">
          <p class="split-status">⚙ Server is splitting tiles…</p>
          <div class="split-progress-bar indeterminate"><div class="split-progress-fill indeterminate-bar"></div></div>
          <p class="split-hint">This may take a moment for large files.</p>
        </template>

        <!-- Stage: ready -->
        <template v-else-if="splitStage === 'ready'">
          <p class="split-status success">✅ Done! {{ splitTileCount }} tiles ready.</p>
          <div class="split-actions">
            <button @click="splitReset">Close</button>
            <button class="split-go" @click="saveSplitZip">💾 Save ZIP…</button>
          </div>
        </template>

        <!-- Stage: saved -->
        <template v-else-if="splitStage === 'saved'">
          <p class="split-status success">✅ Done! ZIP saved.</p>
          <div class="split-actions">
            <button @click="splitReset">Close</button>
          </div>
        </template>

      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session.js'
import { useView2DStore } from '../stores/view2d.js'
import { uploadFile, extractPatch, splitFile, deleteSession, getSessionInfo, getRegions, deletePatch } from '../api/client.js'
import { useToastStore } from '../stores/toast.js'
import { checkFiles } from '../utils/uploadCheck.js'
import CanvasRenderer2D from '../components/view2d/CanvasRenderer2D.vue'
import ScalarSelector from '../components/view2d/ScalarSelector.vue'
import ClassificationLegend from '../components/view2d/ClassificationLegend.vue'
import HelpButton from '../components/common/HelpButton.vue'

const route  = useRoute()
const router = useRouter()
const session = useSessionStore()
const store  = useView2DStore()
const toast  = useToastStore()

const fileInput = ref(null)
const loadingFiles = ref(false)
const loadProgress = ref('')
const dropdownOpen = ref(false)
const extractingWhole = ref(false)
const ready = ref(false)
const uploadingName = ref('')
const removing = ref(false)
const pendingRemove = ref(null)   // { entries, patchCount, counts: { [sessionId]: n } }

// --- Multi-select in the file list ---
const selectedIds = ref(new Set())
let lastCheckedId = null
const selectedEntries = computed(() => session.sessions.filter(s => selectedIds.value.has(s.sessionId)))
const someSelected = computed(() => selectedIds.value.size > 0)
const allSelected = computed(() => session.sessions.length > 0 && selectedIds.value.size === session.sessions.length)

function toggleAll() {
  selectedIds.value = allSelected.value ? new Set() : new Set(session.sessions.map(s => s.sessionId))
}

function onCheckClick(entry, e) {
  const next = new Set(selectedIds.value)
  const select = !next.has(entry.sessionId)
  // Shift+click selects/clears everything between the last clicked box and this one
  if (e.shiftKey && lastCheckedId) {
    const ids = session.sessions.map(s => s.sessionId)
    const a = ids.indexOf(lastCheckedId), b = ids.indexOf(entry.sessionId)
    if (a !== -1 && b !== -1) {
      for (const id of ids.slice(Math.min(a, b), Math.max(a, b) + 1)) {
        select ? next.add(id) : next.delete(id)
      }
    }
  } else {
    select ? next.add(entry.sessionId) : next.delete(entry.sessionId)
  }
  lastCheckedId = entry.sessionId
  selectedIds.value = next
}
const dragActive = ref(false)
let dragDepth = 0

onMounted(async () => {
  const dropped = await session.init()
  if (dropped) toast.warning(`${dropped} file${dropped === 1 ? ' was' : 's were'} no longer on the server and ${dropped === 1 ? 'was' : 'were'} removed from the list.`)

  const id = route.params.id
  if (id) {
    const entry = await session.ensure(id)
    if (entry) {
      session.switchTo(entry)
      if (entry.units?.source === 'uncertain') {
        toast.warning(`Units of ${entry.filename} are uncertain: no coordinate system, and the point density would be very low if it were metres — it may be in feet. Check "Data units" in the 3D view's CHM settings.`)
      }
      await loadRegions(id)
    } else {
      toast.warning('This file is no longer on the server.')
    }
  }
  ready.value = true
})

// Regions are saved on the server, so they survive reloads and file switches
async function loadRegions(id) {
  try {
    const res = await getRegions(id)
    if (id === route.params.id) store.setRegions(res.data.regions)
  } catch (err) {
    if (err.response?.status !== 404) toast.warning('Could not load the saved regions for this file.')
  }
}

// --- Deleting a single patch from the side panel ---
const removingRegion = ref(null)
const pendingRegion = ref(null)

function requestRemoveRegion(region) {
  if (store.labelledPatchIds.has(region.patch_id)) pendingRegion.value = region
  else removeRegion(region)
}

async function removeRegion(region) {
  pendingRegion.value = null
  removingRegion.value = region.patch_id
  try {
    await deletePatch(route.params.id, region.patch_id)
  } catch (err) {
    if (err.response?.status !== 404) {
      removingRegion.value = null
      toast.error(`Could not delete patch_${region.patch_number}: ${err.response?.data?.detail || err.message}`)
      return
    }
  }
  removingRegion.value = null
  store.removeRegion(region.patch_id)
}

const activeEntry = computed(() =>
  session.sessions.find(s => s.sessionId === route.params.id) ?? null
)
const hasActive = computed(() => activeEntry.value !== null)

const currentFilename = computed(() =>
  activeEntry.value?.filename ?? (session.sessions.length ? 'Select a file' : 'No file loaded')
)

const tools = [
  { id: 'rectangle', label: 'Rectangle' },
  { id: 'freehand',  label: 'Freehand'  },
  { id: 'fixed',     label: 'Fixed Rect' },
]

function onFilesSelected(e) {
  const files = Array.from(e.target.files)
  e.target.value = ''
  uploadFiles(files)
}

async function uploadFiles(files) {
  if (loadingFiles.value || !files.length) return

  const { accepted, skipped } = checkFiles(files, session.sessions.map(s => s.filename))
  if (skipped.length) toast.warning(`Skipped ${skipped.join('; ')}`)
  if (!accepted.length) return

  loadingFiles.value = true
  const errors = []
  let firstUploaded = null

  for (let i = 0; i < accepted.length; i++) {
    const file = accepted[i]
    const pos = accepted.length > 1 ? ` ${i + 1}/${accepted.length}` : ''
    uploadingName.value = file.name
    loadProgress.value = `Uploading${pos} · 0%`
    try {
      const res = await uploadFile(file, pct => {
        // After the bytes are sent the server still reads the file and builds its caches
        loadProgress.value = pct >= 100 ? `Processing${pos}…` : `Uploading${pos} · ${pct}%`
      })
      session.addSession(res.data)
      if (!firstUploaded) firstUploaded = res.data
    } catch (err) {
      const detail = err.response?.data?.detail
      errors.push(detail ? `${file.name} (${detail})` : file.name)
    }
  }

  loadingFiles.value = false
  loadProgress.value = ''
  uploadingName.value = ''

  const ok = accepted.length - errors.length
  if (errors.length) toast.error(`Failed to upload: ${errors.join(', ')}`)
  if (ok) toast.success(`Loaded ${ok} file${ok === 1 ? '' : 's'}.`)

  // Nothing open (e.g. all files were removed) → open the first new upload
  if (!hasActive.value && firstUploaded) {
    store.reset()
    session.setSession(firstUploaded)
    router.push(`/session/${firstUploaded.session_id}/view`)
  }
}

// --- Drag & drop anywhere in the view ---
function hasFiles(e) {
  return Array.from(e.dataTransfer?.types ?? []).includes('Files')
}
function onDragEnter(e) {
  if (!hasFiles(e)) return
  dragDepth++
  dragActive.value = true
}
function onDragLeave(e) {
  if (!hasFiles(e)) return
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragActive.value = false
}
function onDrop(e) {
  dragDepth = 0
  dragActive.value = false
  if (!hasFiles(e)) return
  uploadFiles(Array.from(e.dataTransfer.files))
}

function switchSession(entry) {
  dropdownOpen.value = false
  if (entry.sessionId === route.params.id) return
  store.reset()
  session.switchTo(entry)
  router.push(`/session/${entry.sessionId}/view`)
}

// Ask the server how many patches the files have; confirm only if work would be lost
async function requestRemove(entries) {
  if (removing.value || !entries.length) return
  removing.value = true

  const counts = {}
  const alreadyGone = []
  await Promise.all(entries.map(async e => {
    try {
      counts[e.sessionId] = (await getSessionInfo(e.sessionId)).data.patch_count ?? 0
    } catch (err) {
      if (err.response?.status === 404) alreadyGone.push(e)
      else counts[e.sessionId] = 1   // can't tell (backend unreachable) → make the user confirm
    }
  }))
  removing.value = false

  if (alreadyGone.length) {
    finishRemove(alreadyGone.map(e => e.sessionId))
    toast.info(`${alreadyGone.map(e => e.filename).join(', ')} ${alreadyGone.length === 1 ? 'was' : 'were'} already removed from the server.`)
  }
  const remaining = entries.filter(e => e.sessionId in counts)
  if (!remaining.length) return

  const patchCount = remaining.reduce((n, e) => n + counts[e.sessionId], 0)
  // Deleting several files always asks, so a stray "Delete selected" can't wipe the list
  if (patchCount > 0 || remaining.length > 1) {
    dropdownOpen.value = false
    pendingRemove.value = { entries: remaining, patchCount, counts }
  } else {
    await deleteEntries(remaining)
  }
}

async function confirmRemove() {
  const { entries } = pendingRemove.value
  pendingRemove.value = null
  await deleteEntries(entries)
}

async function deleteEntries(entries) {
  removing.value = true
  const results = await Promise.allSettled(entries.map(e => deleteSession(e.sessionId)))
  removing.value = false

  const done = [], failed = []
  results.forEach((r, i) => {
    // 404 = already gone on the server → still remove locally
    if (r.status === 'fulfilled' || r.reason?.response?.status === 404) done.push(entries[i])
    else failed.push(`${entries[i].filename} (${r.reason?.response?.data?.detail || r.reason?.message || 'unknown error'})`)
  })

  if (done.length) {
    finishRemove(done.map(e => e.sessionId))
    toast.info(done.length === 1 ? `Deleted ${done[0].filename}.` : `Deleted ${done.length} files.`)
  }
  if (failed.length) toast.error(`Could not delete: ${failed.join(', ')}`)
}

function finishRemove(ids) {
  const wasActive = ids.includes(route.params.id)
  for (const id of ids) session.removeSession(id)
  selectedIds.value = new Set([...selectedIds.value].filter(id => !ids.includes(id)))
  dropdownOpen.value = false
  if (!wasActive) return
  store.reset()
  if (session.sessionId) {
    router.push(`/session/${session.sessionId}/view`)
  }
  // Last file removed: hasActive becomes false and the empty state is shown
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
const splitModal    = ref(false)
const splitNTiles   = ref(4)
const splitSelectedFile = ref(null)
const splitStage    = ref('idle')   // 'idle' | 'uploading' | 'splitting' | 'ready'
const splitUploadPct = ref(0)
const splitZipBlob  = ref(null)
const splitZipName  = ref('')
const splitTileCount = ref(0)

function onSplitFileSelected(e) {
  splitSelectedFile.value = e.target.files[0] || null
}

function splitReset() {
  splitModal.value    = false
  splitStage.value    = 'idle'
  splitSelectedFile.value = null
  splitZipBlob.value  = null
  splitUploadPct.value = 0
  splitTileCount.value = 0
}

async function doSplit() {
  if (!splitSelectedFile.value) return
  splitZipName.value = splitSelectedFile.value.name.replace(/\.[^.]+$/, '') + '.zip'
  splitStage.value   = 'uploading'
  splitUploadPct.value = 0
  try {
    const res = await splitFile(
      splitSelectedFile.value,
      splitNTiles.value,
      pct => {
        splitUploadPct.value = pct
        if (pct >= 100) splitStage.value = 'splitting'
      }
    )
    // Count tiles from ZIP (use Content-Disposition or just store nTiles)
    splitZipBlob.value  = res.data
    splitTileCount.value = splitNTiles.value   // exact count from server isn't exposed; close enough
    splitStage.value    = 'ready'
  } catch (err) {
    splitStage.value = 'idle'
    toast.error('Split failed: ' + (err.message || 'unknown error'))
  }
}

async function saveSplitZip() {
  const blob = splitZipBlob.value
  if (!blob) return
  try {
    if (window.showSaveFilePicker) {
      const handle = await window.showSaveFilePicker({
        suggestedName: splitZipName.value,
        types: [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }],
      })
      const writable = await handle.createWritable()
      await writable.write(blob)
      await writable.close()
    } else {
      // Fallback: browser-chosen downloads folder
      const url = URL.createObjectURL(blob)
      const a   = document.createElement('a')
      a.href    = url
      a.download = splitZipName.value
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
    splitStage.value = 'saved'
  } catch (err) {
    if (err.name !== 'AbortError') toast.error('Save failed: ' + err.message)
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
.empty-state {
  flex: 1;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 10px;
  color: #889;
}
.empty-title { font-size: 18px; color: #adf; font-weight: 600; }
.empty-hint { font-size: 13px; margin-bottom: 6px; }
.empty-state .load-btn { padding: 8px 18px; font-size: 14px; }
.empty-drop { font-size: 12px; color: #667; }
.view2d-layout { position: relative; }
.drop-overlay {
  position: absolute; inset: 8px;
  border: 2px dashed #7ab3ff; border-radius: 12px;
  background: rgba(20, 30, 60, 0.85);
  display: flex; align-items: center; justify-content: center;
  z-index: 500; pointer-events: none;
}
.drop-overlay p { color: #adf; font-size: 18px; font-weight: 600; }
.confirm-text { margin: 0; font-size: 13px; line-height: 1.5; color: #aab; max-width: 420px; }
.confirm-text strong { color: #fff; }
.danger-btn { background: #5a2a2e; border-color: #a44; color: #fcc; }
.confirm-list {
  margin: 0; padding: 8px 12px 8px 28px; max-height: 180px; overflow-y: auto;
  background: #0d0d1f; border: 1px solid #2a2a44; border-radius: 6px;
  font-size: 12px; color: #aac; line-height: 1.6;
}
.confirm-count { color: #fb4; }

/* Multi-select in file list */
.dropdown-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 6px 10px; background: #14142a; border-bottom: 1px solid #2a2a44;
}
.select-all { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #889; cursor: pointer; }
.bulk-delete { background: #5a2a2e; border-color: #a44; color: #fcc; padding: 3px 10px; font-size: 12px; }
.bulk-delete:hover:not(:disabled) { background: #7a3035; }
.dropdown-list { max-height: 50vh; overflow-y: auto; }
.item-check { margin-right: 10px; flex-shrink: 0; cursor: pointer; accent-color: #7ab3ff; }
.select-all input { accent-color: #7ab3ff; }
.dropdown-item.selected:not(.active) { background: #221f3a; }
.danger-btn:hover:not(:disabled) { background: #7a3035; }
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
.dataset-btn {
  background: #2a2a4e; color: #cce; border: 1px solid #445; padding: 5px 12px;
  border-radius: 6px; font-size: 13px; text-decoration: none; white-space: nowrap;
}
.dataset-btn:hover { background: #3a3a6e; }

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
  min-width: 380px;
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
.split-status { margin: 0; font-size: 14px; color: #adf; font-weight: 500; }
.split-status.success { color: #7fa; }
.split-hint { margin: 0; font-size: 12px; color: #668; }
.split-pct { margin: 0; font-size: 12px; color: #7af; text-align: right; }

/* Progress bar */
.split-progress-bar {
  height: 6px; background: #223; border-radius: 3px; overflow: hidden;
}
.split-progress-fill {
  height: 100%; background: #4af; border-radius: 3px;
  transition: width 0.2s;
}
/* Indeterminate animation */
.split-progress-bar.indeterminate { position: relative; }
@keyframes indeterminate {
  0%   { left: -40%; width: 40%; }
  100% { left: 100%; width: 40%; }
}
.indeterminate-bar {
  position: absolute; width: 40%;
  animation: indeterminate 1.2s ease-in-out infinite;
}

.split-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 4px; }
.split-go { background: #2a5a3e; border-color: #4a9a6e; color: #afa; }
.split-go:hover:not(:disabled) { background: #3a6a4e; }
</style>
