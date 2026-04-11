<template>
  <div
    class="dropzone"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop.prevent="onDrop"
    @click="inputRef.click()"
  >
    <input ref="inputRef" type="file" accept=".las,.LAS,.laz,.LAZ" multiple style="display:none" @change="onFileChange" />
    <template v-if="!uploading">
      <p class="icon">📂</p>
      <p>Drop <code>.las</code> / <code>.laz</code> files here or <strong>click to browse</strong></p>
      <p class="hint">Multiple files supported</p>
    </template>
    <div v-else class="progress-wrap">
      <p class="progress-file">{{ currentFile }}</p>
      <div class="progress-bar-track">
        <div class="progress-bar" :style="{ width: progress + '%' }"></div>
      </div>
      <p class="progress-label">{{ fileIndex + 1 }} / {{ totalFiles }} — {{ progress }}%</p>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { uploadFile } from '../../api/client.js'
import { useSessionStore } from '../../stores/session.js'
import { useRouter } from 'vue-router'

const dragging = ref(false)
const uploading = ref(false)
const progress = ref(0)
const currentFile = ref('')
const fileIndex = ref(0)
const totalFiles = ref(0)
const error = ref(null)
const inputRef = ref(null)
const session = useSessionStore()
const router = useRouter()

async function onDrop(e) {
  if (uploading.value) return
  dragging.value = false
  const files = Array.from(e.dataTransfer.files).filter(f => f.name.match(/\.(las|laz)$/i))
  if (files.length) await uploadAll(files)
}

async function onFileChange(e) {
  if (uploading.value) return
  const files = Array.from(e.target.files)
  e.target.value = ''
  if (files.length) await uploadAll(files)
}

async function uploadAll(files) {
  uploading.value = true
  error.value = null
  totalFiles.value = files.length
  let firstSessionId = null
  const errors = []

  for (let i = 0; i < files.length; i++) {
    fileIndex.value = i
    currentFile.value = files[i].name
    progress.value = 0
    try {
      const res = await uploadFile(files[i], p => { progress.value = p })
      if (i === 0) {
        session.setSession(res.data)
        firstSessionId = res.data.session_id
      } else {
        session.addSession(res.data)
      }
    } catch (err) {
      errors.push(files[i].name)
    }
  }

  uploading.value = false

  if (errors.length) {
    error.value = `Failed: ${errors.join(', ')}`
  }

  if (firstSessionId) {
    router.push(`/session/${firstSessionId}/view`)
  }
}
</script>

<style scoped>
.dropzone {
  border: 2px dashed #4a5a7a;
  border-radius: 16px;
  padding: 60px 40px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  max-width: 480px;
  width: 100%;
  background: rgba(255,255,255,0.03);
}
.dropzone.dragging { border-color: #7ab3ff; background: rgba(122,179,255,0.08); }
.dropzone:hover { border-color: #6090cc; }
.icon { font-size: 3rem; margin-bottom: 12px; }
p { color: #aac; line-height: 1.6; }
.hint { font-size: 12px; color: #667; margin-top: 6px; }
code { color: #7af; font-family: monospace; }
strong { color: #eee; }
.progress-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.progress-file { font-size: 13px; color: #adf; font-family: monospace; }
.progress-bar-track {
  width: 100%;
  height: 8px;
  background: #2a3a5a;
  border-radius: 4px;
  overflow: hidden;
}
.progress-bar { height: 100%; background: #4af; transition: width 0.15s; border-radius: 4px; }
.progress-label { font-size: 13px; color: #aac; }
.error { color: #f77; margin-top: 16px; font-size: 14px; }
</style>
