<template>
  <router-view :key="$route.fullPath" />
  <ToastHost />
</template>

<script setup>
import ToastHost from './components/common/ToastHost.vue'
</script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #1a1a2e; color: #eee; font-family: system-ui, sans-serif; }
</style>
