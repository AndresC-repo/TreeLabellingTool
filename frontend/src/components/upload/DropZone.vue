<template>
  <div
    class="dropzone"
    :class="{ dragging }"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop.prevent="onDrop"
    @click="inputRef.click()"
  >
    <input ref="inputRef" type="file" accept=".las,.LAS" style="display:none" @change="onFileChange" />
    <template v-if="!uploading">
      <p class="icon">📂</p>
      <p>Drop a <code>.las</code> file here or <strong>click to browse</strong></p>
    </template>
    <div v-else class="progress-wrap">
      <div class="progress-bar" :style="{ width: progress + '%' }"></div>
      <span>Uploading… {{ progress }}%</span>
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
const error = ref(null)
const inputRef = ref(null)
const session = useSessionStore()
const router = useRouter()

async function onDrop(e) {
  dragging.value = false
  const file = e.dataTransfer.files[0]
  if (file) await upload(file)
}

async function onFileChange(e) {
  const file = e.target.files[0]
  if (file) await upload(file)
}

async function upload(file) {
  if (!file.name.match(/\.las$/i)) {
    error.value = 'Only .las files are supported'
    return
  }
  uploading.value = true
  error.value = null
  progress.value = 0
  try {
    const res = await uploadFile(file, p => { progress.value = p })
    session.setSession(res.data)
    router.push(`/session/${res.data.session_id}/view`)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Upload failed. Please try again.'
  } finally {
    uploading.value = false
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
code { color: #7af; font-family: monospace; }
strong { color: #eee; }
.progress-wrap {
  height: 10px;
  background: #2a3a5a;
  border-radius: 5px;
  overflow: hidden;
  margin-bottom: 12px;
  position: relative;
}
.progress-bar { height: 100%; background: #4af; transition: width 0.15s; border-radius: 5px; }
.progress-wrap span {
  position: absolute;
  top: 14px;
  left: 0; right: 0;
  text-align: center;
  font-size: 13px;
  color: #aac;
}
.error { color: #f77; margin-top: 16px; font-size: 14px; }
</style>
