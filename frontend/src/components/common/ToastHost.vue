<template>
  <teleport to="body">
    <div class="toast-host">
      <transition-group name="toast">
        <div
          v-for="t in toast.toasts"
          :key="t.id"
          class="toast"
          :class="t.type"
          role="status"
          @click="toast.dismiss(t.id)"
        >{{ t.message }}</div>
      </transition-group>
    </div>
  </teleport>
</template>

<script setup>
import { useToastStore } from '../../stores/toast.js'
const toast = useToastStore()
</script>

<style scoped>
.toast-host {
  position: fixed; right: 16px; bottom: 16px;
  display: flex; flex-direction: column; gap: 8px;
  z-index: 2000; max-width: 380px;
  pointer-events: none;
}
.toast {
  pointer-events: auto; cursor: pointer;
  background: #1a1a30; color: #cce;
  border: 1px solid #445; border-left: 4px solid #7ab3ff;
  border-radius: 8px; padding: 10px 14px;
  font-size: 13px; line-height: 1.4;
  box-shadow: 0 6px 20px rgba(0,0,0,0.45);
}
.toast.success { border-left-color: #5c9; }
.toast.warning { border-left-color: #fb4; }
.toast.error   { border-left-color: #f66; color: #fcc; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(8px); }
.toast-enter-active, .toast-leave-active { transition: opacity 0.2s, transform 0.2s; }
</style>
