<template>
  <div class="save-panel">
    <h3>Save</h3>

    <label class="field">
      <span>City</span>
      <input
        v-model="city"
        :placeholder="info.state ? `e.g. Gainesville (else ${info.state})` : 'e.g. Gainesville'"
        @change="saveCity"
        title="Stored for the whole source tile; used at the start of the file name"
      />
    </label>

    <div class="name-row">
      <input v-model="filename" @input="customName = true" placeholder="automatic name" spellcheck="false" />
      <button v-if="customName" class="auto-btn" @click="useAutoName" title="Back to the automatic name">↺</button>
    </div>
    <p class="name-hint">
      {{ info.trees }} tree{{ info.trees === 1 ? '' : 's' }} · patch {{ info.patch_number ?? '–' }}
      <span v-if="info.current_file && info.current_file !== filename" class="dim">
        · replaces {{ info.current_file }}
      </span>
    </p>

    <label class="check">
      <input type="checkbox" v-model="toLabels" />
      <span>Save to training labels <code>data/labels</code></span>
    </label>
    <p v-if="toLabels && info.labels_folder_connected === false" class="warn">
      Labels folder not connected — the file is kept inside Docker. See README / docker-compose.
    </p>

    <button @click="save" :disabled="saving" class="save-btn" title="Save [Ctrl+S]">
      {{ saving ? 'Saving...' : 'Save as .las' }} <kbd>Ctrl+S</kbd>
    </button>
    <div v-if="lastSaved" class="saved">
      ✓ {{ lastSaved.output_filename }}
      <span v-if="lastSaved.saved_to" class="dim to">saved to data/labels</span>
    </div>
    <div v-if="downloadUrl" class="download-row">
      <a :href="downloadUrl" download>⬇ Download labeled .las</a>
      <router-link to="/dataset" class="dataset-link">📊 Dataset overview</router-link>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { savePatch, getDownloadUrl, restoreFromClient, getExportName, updateDatasetSource } from '../../api/client.js'
import { useRoute } from 'vue-router'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { getPatchCache } from '../../composables/pointCloudCache.js'
import { useToastStore } from '../../stores/toast.js'

const route = useRoute()
const patchStore = usePatch3DStore()
const toast = useToastStore()

const saving = ref(false)
const downloadUrl = ref(null)
const error = ref(null)
const lastSaved = ref(null)
const toLabels = ref(true)

// Automatic name from the server: <city or state>_<tile>_p<n>_t<trees>.las
const info = ref({ trees: 0, patch_number: null, state: '', city: '', current_file: null, labels_folder_connected: null })
const filename = ref('')
const customName = ref(false)
const city = ref('')

async function refreshName() {
  try {
    const res = await getExportName(route.params.id, route.params.patchId)
    info.value = res.data
    if (!customName.value) filename.value = res.data.suggested
    if (document.activeElement?.closest?.('.field') == null) city.value = res.data.city || ''
  } catch { /* patch not ready yet */ }
}
function useAutoName() {
  customName.value = false
  refreshName()
}
async function saveCity() {
  try {
    await updateDatasetSource(info.value.source, { city: city.value.trim() })
    customName.value = false
    await refreshName()
  } catch (err) {
    toast.error('Could not save the city: ' + (err.response?.data?.detail || err.message))
  }
}

onMounted(refreshName)
let nameTimer = null
watch(() => patchStore.labelsVersion, () => {   // tree count changes with every label edit
  clearTimeout(nameTimer)
  nameTimer = setTimeout(refreshName, 300)
})

defineExpose({ save })

async function tryRestorePatch() {
  const { positions, origCls, origin } = getPatchCache()
  if (!positions || !origCls) return false
  const n = positions.length / 3
  const buf = new Float32Array(n * 4)
  for (let i = 0; i < n; i++) {
    buf[i*4]   = positions[i*3]
    buf[i*4+1] = positions[i*3+1]
    buf[i*4+2] = positions[i*3+2]
    buf[i*4+3] = origCls[i]
  }
  try {
    await restoreFromClient(route.params.id, route.params.patchId, buf.buffer, origin)
    return true
  } catch {
    return false
  }
}

async function doSave() {
  const res = await savePatch(route.params.id, route.params.patchId, customName.value ? filename.value : null, toLabels.value)
  lastSaved.value = res.data
  downloadUrl.value = getDownloadUrl(route.params.id, route.params.patchId)
  customName.value = false
  await refreshName()
  toast.success(res.data.saved_to
    ? `Saved ${res.data.output_filename} to data/labels (${res.data.trees} trees)`
    : `Saved ${res.data.output_filename}`)
}

async function save() {
  saving.value = true
  error.value = null
  try {
    await doSave()
  } catch (err) {
    if (err.response?.status === 404) {
      error.value = 'Recovering patch data from browser…'
      const recovered = await tryRestorePatch()
      if (recovered) {
        try {
          await doSave()
          error.value = null
          return
        } catch (e2) {
          error.value = e2.response?.data?.detail || 'Save failed after recovery'
        }
      } else {
        error.value = 'Server lost patch file and browser cache is empty — please reload the page'
      }
    } else {
      error.value = err.response?.data?.detail || 'Save failed'
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.save-panel { color: #eee; }
h3 { color: #adf; margin-bottom: 12px; font-size: 14px; font-weight: 600; }
input {
  width: 100%;
  background: #2a2a4e; color: #eee;
  border: 1px solid #556; padding: 8px;
  border-radius: 4px; margin-bottom: 8px; font-size: 12px;
  font-family: monospace;
}
.save-btn {
  width: 100%; padding: 10px;
  background: #2a5a3e; border: none;
  border-radius: 6px; color: #eee; cursor: pointer; font-size: 14px;
}
.save-btn:hover:not(:disabled) { background: #3a6a4e; }
.save-btn:disabled { opacity: 0.4; cursor: default; }
.download-row { margin-top: 10px; display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.dataset-link { color: #9c9; font-size: 13px; text-decoration: none; }
.dataset-link:hover { text-decoration: underline; }
.field { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.field span { font-size: 12px; color: #889; width: 32px; }
.field input { margin-bottom: 0; font-family: inherit; }
.name-row { display: flex; gap: 4px; }
.name-row input { flex: 1; }
.auto-btn {
  height: 33px; padding: 0 9px; background: #2a2a4e; color: #adf;
  border: 1px solid #556; border-radius: 4px; cursor: pointer;
}
.name-hint { font-size: 11px; color: #889; margin: -2px 0 8px; }
.dim { color: #667; }
.check { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #aab; margin-bottom: 8px; cursor: pointer; }
.check input { width: auto; margin: 0; }
.check code { color: #7af; font-size: 11px; }
.warn { font-size: 11px; color: #fb4; margin: -4px 0 8px; line-height: 1.4; }
.saved { margin-top: 8px; font-size: 12px; color: #7c9; font-family: monospace; word-break: break-all; }
.saved .to { display: block; font-family: system-ui, sans-serif; font-size: 11px; }
a { color: #7af; font-size: 13px; }
.error { color: #f66; margin-top: 8px; font-size: 12px; }
kbd {
  display: inline-block; font-size: 9px; font-family: monospace;
  background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
  border-radius: 3px; padding: 0 3px; margin-left: 4px;
  line-height: 1.6; color: #9b9; vertical-align: middle;
}
</style>
