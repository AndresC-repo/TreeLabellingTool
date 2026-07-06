<template>
  <div class="save-panel">
    <h3>Save</h3>
    <input v-model="filename" placeholder="output.las" />
    <button @click="save" :disabled="saving" class="save-btn" title="Save [Ctrl+S]">
      {{ saving ? 'Saving...' : 'Save as .las' }} <kbd>Ctrl+S</kbd>
    </button>
    <div v-if="downloadUrl" class="download-row">
      <a :href="downloadUrl" download>⬇ Download labeled .las</a>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { savePatch, getDownloadUrl, restoreFromClient } from '../../api/client.js'
import { useRoute } from 'vue-router'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useSessionStore } from '../../stores/session.js'
import { getPatchCache } from '../../composables/pointCloudCache.js'

const route = useRoute()
const patchStore = usePatch3DStore()
const session = useSessionStore()

const saving = ref(false)
const downloadUrl = ref(null)
const error = ref(null)

// Auto-generate: tree_las_patch_1_101_102.las
const suggestedFilename = computed(() => {
  const stem = (session.filename ?? 'output').replace(/\.la[sz]$/i, '')
  if (patchStore.isWholePatch) return `${stem}.las`
  const n = patchStore.patchNumber
  const labels = [...patchStore.appliedLabels].sort((a, b) => a - b)
  if (labels.length === 0) return `${stem}_patch_${n}.las`
  const instances = labels.filter(l => l >= 201)
  if (instances.length >= 2) {
    const first = instances[0], last = instances[instances.length - 1]
    const nonInstance = labels.filter(l => l < 201)
    const prefix = nonInstance.length ? `${nonInstance.join('_')}_` : ''
    return `${stem}_patch_${n}_${prefix}${first}_${last}__t${instances.length}.las`
  }
  return `${stem}_patch_${n}_${labels.join('_')}.las`
})

const filename = ref(suggestedFilename.value)
// Update whenever labels are added or patch number is set
watch(suggestedFilename, v => { filename.value = v })

defineExpose({ save })

async function tryRestorePatch() {
  const { positions, origCls } = getPatchCache()
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
    await restoreFromClient(route.params.id, route.params.patchId, buf.buffer)
    return true
  } catch {
    return false
  }
}

async function save() {
  saving.value = true
  error.value = null
  try {
    await savePatch(route.params.id, route.params.patchId, filename.value)
    downloadUrl.value = getDownloadUrl(route.params.id, route.params.patchId)
  } catch (err) {
    if (err.response?.status === 404) {
      error.value = 'Recovering patch data from browser…'
      const recovered = await tryRestorePatch()
      if (recovered) {
        try {
          await savePatch(route.params.id, route.params.patchId, filename.value)
          downloadUrl.value = getDownloadUrl(route.params.id, route.params.patchId)
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
.download-row { margin-top: 12px; text-align: center; }
a { color: #7af; font-size: 14px; }
.error { color: #f66; margin-top: 8px; font-size: 12px; }
kbd {
  display: inline-block; font-size: 9px; font-family: monospace;
  background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
  border-radius: 3px; padding: 0 3px; margin-left: 4px;
  line-height: 1.6; color: #9b9; vertical-align: middle;
}
</style>
