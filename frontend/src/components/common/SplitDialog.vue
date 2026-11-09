<template>
  <teleport to="body">
    <div v-if="open" class="split-overlay" @click.self="stage === 'idle' && close()">
      <div class="split-box">
        <h3>✂ Split a LAS / LAZ into tiles</h3>

        <template v-if="stage === 'idle'">
          <p class="split-hint">For files too big to work with in one piece. The file is cut into a grid of tiles.</p>
          <div class="split-row">
            <label>File</label>
            <input type="file" accept=".las,.LAS,.laz,.LAZ" @change="e => (file = e.target.files[0] || null)" />
          </div>
          <div class="split-row">
            <label>Tiles</label>
            <select v-model.number="nTiles">
              <option :value="4">4 tiles  (2 × 2)</option>
              <option :value="8">8 tiles  (2 × 4)</option>
              <option :value="16">16 tiles (4 × 4)</option>
              <option :value="32">32 tiles (4 × 8)</option>
            </select>
          </div>
          <div class="split-row mode">
            <label>Then</label>
            <div class="modes">
              <label class="mode-opt">
                <input type="radio" value="load" v-model="mode" />
                <span>Load the tiles here, grouped in a folder<template v-if="file"> 📁 {{ stem }}</template></span>
              </label>
              <label class="mode-opt">
                <input type="radio" value="zip" v-model="mode" />
                <span>Download them as a ZIP</span>
              </label>
            </div>
          </div>
          <div class="split-actions">
            <button @click="close">Cancel</button>
            <button class="split-go" :disabled="!file" @click="run">{{ mode === 'load' ? 'Split & load' : 'Split & download' }}</button>
          </div>
        </template>

        <template v-else-if="stage === 'uploading'">
          <p class="split-status">⬆ Uploading {{ file?.name }}…</p>
          <div class="split-progress-bar"><div class="split-progress-fill" :style="{ width: pct + '%' }"></div></div>
          <p class="split-pct">{{ pct }}%</p>
        </template>

        <template v-else-if="stage === 'splitting'">
          <p class="split-status">⚙ Splitting{{ mode === 'load' ? ' and loading the tiles' : '' }}…</p>
          <div class="split-progress-bar indeterminate"><div class="split-progress-fill indeterminate-bar"></div></div>
          <p class="split-hint">This may take a moment for large files.</p>
        </template>

        <template v-else-if="stage === 'loaded'">
          <p class="split-status success">✅ {{ loadedCount }} tiles loaded in 📁 {{ loadedFolder }}.</p>
          <div class="split-actions">
            <button @click="close">Close</button>
            <button class="split-go" @click="openFirst">Open the first tile</button>
          </div>
        </template>

        <template v-else-if="stage === 'ready'">
          <p class="split-status success">✅ {{ nTiles }} tiles ready.</p>
          <div class="split-actions">
            <button @click="close">Close</button>
            <button class="split-go" @click="saveZip">💾 Save ZIP…</button>
          </div>
        </template>

        <template v-else-if="stage === 'saved'">
          <p class="split-status success">✅ ZIP saved.</p>
          <div class="split-actions"><button @click="close">Close</button></div>
        </template>
      </div>
    </div>
  </teleport>
</template>

<script setup>
// Split a large LAS/LAZ into a grid of tiles, then load them into the tool as one folder
// or download them as a ZIP. Used on the start page and in the 2D view.
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { splitFile } from '../../api/client.js'
import { useSessionStore } from '../../stores/session.js'
import { useToastStore } from '../../stores/toast.js'

const props = defineProps({ open: { type: Boolean, default: false } })
const emit = defineEmits(['update:open', 'loaded'])

const router = useRouter()
const session = useSessionStore()
const toast = useToastStore()

const file = ref(null)
const nTiles = ref(4)
const mode = ref('load')          // 'load' | 'zip'
const stage = ref('idle')         // idle | uploading | splitting | loaded | ready | saved
const pct = ref(0)
const zipBlob = ref(null)
const loadedFolder = ref('')
const loadedTiles = ref([])
const loadedCount = computed(() => loadedTiles.value.length)
const stem = computed(() => (file.value?.name || '').replace(/\.[^.]+$/, ''))

function close() {
  emit('update:open', false)
  stage.value = 'idle'; file.value = null; zipBlob.value = null; pct.value = 0
  loadedTiles.value = []; loadedFolder.value = ''
}

async function run() {
  if (!file.value) return
  stage.value = 'uploading'; pct.value = 0
  const load = mode.value === 'load'
  try {
    const res = await splitFile(file.value, nTiles.value, p => {
      pct.value = p
      if (p >= 100) stage.value = 'splitting'
    }, load)
    if (load) {
      for (const t of res.data.tiles) session.addSession(t)
      loadedTiles.value = res.data.tiles
      loadedFolder.value = res.data.folder
      stage.value = 'loaded'
      emit('loaded', res.data)
    } else {
      zipBlob.value = res.data
      stage.value = 'ready'
    }
  } catch (err) {
    stage.value = 'idle'
    let detail = err.response?.data?.detail
    if (err.response?.data instanceof Blob) {   // ZIP mode: the error body comes back as a blob
      try { detail = JSON.parse(await err.response.data.text()).detail } catch { /* keep */ }
    }
    toast.error('Split failed: ' + (detail || err.message || 'unknown error'))
  }
}

function openFirst() {
  const first = loadedTiles.value[0]
  if (!first) return close()
  const entry = session.sessions.find(s => s.sessionId === first.session_id)
  if (entry) session.switchTo(entry)
  close()
  router.push(`/session/${first.session_id}/view`)
}

async function saveZip() {
  const blob = zipBlob.value
  if (!blob) return
  const name = `${stem.value}.zip`
  try {
    if (window.showSaveFilePicker) {
      const handle = await window.showSaveFilePicker({
        suggestedName: name,
        types: [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }],
      })
      const writable = await handle.createWritable()
      await writable.write(blob)
      await writable.close()
    } else {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = name
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
    stage.value = 'saved'
  } catch (err) {
    if (err.name !== 'AbortError') toast.error('Save failed: ' + err.message)
  }
}
</script>

<style scoped>
.split-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.65);
  display: flex; align-items: center; justify-content: center; z-index: 200;
}
.split-box {
  background: #12122a; border: 1px solid #335; border-radius: 10px;
  padding: 24px 28px; min-width: 380px; max-width: 460px;
  display: flex; flex-direction: column; gap: 14px; color: #dde;
}
.split-box h3 { margin: 0; color: #adf; font-size: 1.1rem; }
.split-row { display: flex; align-items: center; gap: 12px; }
.split-row.mode { align-items: flex-start; }
.split-row > label { width: 44px; color: #889; font-size: 13px; flex-shrink: 0; }
.split-row select, .split-row input[type=file] {
  flex: 1; background: #1a1a35; color: #cce; border: 1px solid #335; border-radius: 4px; padding: 4px 6px; font-size: 13px;
}
.modes { display: flex; flex-direction: column; gap: 6px; }
.mode-opt { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #cce; cursor: pointer; }
.split-status { margin: 0; font-size: 14px; color: #adf; font-weight: 500; }
.split-status.success { color: #7fa; }
.split-hint { margin: 0; font-size: 12px; color: #778; }
.split-pct { margin: 0; font-size: 12px; color: #7af; text-align: right; }
.split-progress-bar { height: 8px; background: #1a1a35; border-radius: 4px; overflow: hidden; position: relative; }
.split-progress-fill { height: 100%; background: linear-gradient(90deg, #3a6aff, #5af); transition: width 0.2s; }
.indeterminate-bar { width: 40%; position: absolute; animation: slide 1.2s ease-in-out infinite; }
@keyframes slide { 0% { left: -40%; } 100% { left: 100%; } }
.split-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 4px; }
.split-actions button {
  background: #2a2a4e; color: #cce; border: 1px solid #446; border-radius: 6px; padding: 6px 14px; font-size: 13px; cursor: pointer;
}
.split-actions button:hover:not(:disabled) { background: #3a3a6e; }
.split-actions button:disabled { opacity: 0.5; cursor: default; }
.split-go { background: #2a5a3e !important; border-color: #4a9a6e !important; color: #afa !important; }
.split-go:hover:not(:disabled) { background: #3a6a4e !important; }
</style>
