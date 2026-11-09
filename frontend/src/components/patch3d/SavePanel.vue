<template>
  <div class="save-panel">
    <h3>Save</h3>

    <label v-if="!info.custom_name" class="field">
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
      {{ info.trees }} tree{{ info.trees === 1 ? '' : 's' }}<template v-if="info.patch_number"> · patch {{ info.patch_number }}</template>
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

    <!-- Units the file will be tagged with — what the training importer trusts -->
    <p class="units-line" :class="{ bad: unitConflict }"
       :title="'The saved file is tagged with these units; the training importer converts to metres from them.'">
      Units: <b>{{ UNIT_NAMES[patchStore.unitCode] }}</b>
      <span class="dim">({{ unitConflict ? 'set by hand — the file says ' + UNIT_NAMES[patchStore.unitCrs] : unitSrc }})</span>
      <button v-if="unitConflict" class="fix-units" @click="useFileUnits">Use {{ UNIT_NAMES[patchStore.unitCrs] }}</button>
    </p>

    <!-- Export check failed: say why, offer the fix or saving anyway -->
    <div v-if="unitsProblems.length" class="units-check">
      <p class="uc-title">⚠ The units look wrong for this patch:</p>
      <ul><li v-for="p in unitsProblems" :key="p">{{ p }}</li></ul>
      <div class="uc-actions">
        <button v-if="unitConflict" class="fix-units" @click="useFileUnits(true)">Use {{ UNIT_NAMES[patchStore.unitCrs] }} and save</button>
        <button class="anyway" @click="saveAnyway">Save anyway</button>
        <button class="cancel" @click="unitsProblems = []">Cancel</button>
      </div>
    </div>

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
import { ref, watch, onMounted, computed } from 'vue'
import { savePatch, getDownloadUrl, restoreFromClient, getExportName, updateDatasetSource, setUnits } from '../../api/client.js'
import { useRoute } from 'vue-router'
import { usePatch3DStore, UNIT_NAMES } from '../../stores/patch3d.js'
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

// ── Units ──
const unitsProblems = ref([])
const unitConflict = computed(() => !!patchStore.unitCrs && patchStore.unitCode !== patchStore.unitCrs)
const unitSrc = computed(() => ({ crs: 'from the file', guess: 'guessed', user: 'set by you', default: 'assumed',
  uncertain: 'uncertain — check', export: 'from an earlier export' })[patchStore.unitSource] ?? patchStore.unitSource)
async function useFileUnits(thenSave = false) {
  try {
    const res = await setUnits(route.params.id, patchStore.unitCrs)
    patchStore.unitCode = res.data.code; patchStore.unitScale = res.data.scale; patchStore.unitSource = res.data.source
    toast.info(`Units set to ${res.data.name}.`)
    if (thenSave === true) { unitsProblems.value = []; await save() }
  } catch (err) {
    error.value = 'Could not change units — see console'
    console.error(err)
  }
}
async function saveAnyway() {
  unitsProblems.value = []
  await save(true)
}

async function doSave(confirmUnits = false) {
  const res = await savePatch(route.params.id, route.params.patchId, customName.value ? filename.value : null, toLabels.value, confirmUnits)
  lastSaved.value = res.data
  downloadUrl.value = getDownloadUrl(route.params.id, route.params.patchId)
  customName.value = false
  await refreshName()
  toast.success(res.data.saved_to
    ? `Saved ${res.data.output_filename} to data/labels (${res.data.trees} trees)`
    : `Saved ${res.data.output_filename}`)
}

async function save(confirmUnits = false) {
  saving.value = true
  error.value = null
  try {
    await doSave(confirmUnits === true)
    unitsProblems.value = []
  } catch (err) {
    const detail = err.response?.data?.detail
    if (err.response?.status === 409 && detail?.code === 'units_check') {
      unitsProblems.value = detail.problems
    } else if (err.response?.status === 404) {
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
      const d = err.response?.data?.detail
      error.value = (typeof d === 'string' ? d : d?.message) || 'Save failed'
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.save-panel { color: #eee; }
h3 { color: #adf; margin-bottom: 12px; font-size: 14px; font-weight: 600; }
.units-line { font-size: 11.5px; color: #9ab; margin: 0 0 8px; }
.units-line b { color: #dde; font-weight: 600; }
.units-line.bad { color: #ff9a8a; }
.units-line.bad b { color: #ffb4a8; }
.fix-units { margin-left: 6px; font-size: 11px; padding: 2px 8px; border-radius: 4px; cursor: pointer; border: 1px solid #3c7a55; background: #1f3a2c; color: #9e9; }
.units-check { font-size: 11.5px; color: #ecc; background: #2a1820; border: 1px solid #6a3440; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; }
.units-check .uc-title { font-weight: 600; color: #ffb4a8; margin-bottom: 4px; }
.units-check ul { padding-left: 16px; display: flex; flex-direction: column; gap: 3px; }
.uc-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.uc-actions button { font-size: 11px; padding: 3px 9px; border-radius: 4px; cursor: pointer; }
.uc-actions .fix-units { margin-left: 0; }
.uc-actions .anyway { border: 1px solid #7a3c44; background: #3a1f24; color: #f99; }
.uc-actions .cancel { border: 1px solid #445; background: #223; color: #aab; }
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
