<template>
  <div class="save-panel">
    <h3>Save</h3>
    <input v-model="filename" placeholder="patch_labeled.las" />
    <button @click="save" :disabled="saving" class="save-btn">
      {{ saving ? 'Saving...' : 'Save as .las' }}
    </button>
    <div v-if="downloadUrl" class="download-row">
      <a :href="downloadUrl" download>⬇ Download labeled .las</a>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { savePatch, getDownloadUrl } from '../../api/client.js'
import { useRoute } from 'vue-router'

const route = useRoute()
const filename = ref('patch_labeled.las')
const saving = ref(false)
const downloadUrl = ref(null)
const error = ref(null)

async function save() {
  saving.value = true
  error.value = null
  try {
    await savePatch(route.params.id, route.params.patchId, filename.value)
    downloadUrl.value = getDownloadUrl(route.params.id, route.params.patchId)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Save failed'
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
  border-radius: 4px; margin-bottom: 8px; font-size: 13px;
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
</style>
