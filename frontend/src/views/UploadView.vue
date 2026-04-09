<template>
  <div class="upload-page">
    <div class="header">
      <h1>Point Cloud Labeling Tool</h1>
      <p class="subtitle">Upload a <code>.las</code> or <code>.laz</code> file to begin labeling</p>
    </div>
    <DropZone />
  </div>
</template>

<script setup>
import DropZone from '../components/upload/DropZone.vue'
</script>

<style scoped>
.upload-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  gap: 40px;
  padding: 24px;
}
.header { text-align: center; }
h1 { font-size: 2.2rem; color: #adf; font-weight: 600; margin-bottom: 8px; }
.subtitle { color: #889; font-size: 1rem; }
code { color: #7af; }
</style>
