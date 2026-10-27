import { defineStore } from 'pinia'
import { ref } from 'vue'

let _nextId = 1

export const useToastStore = defineStore('toast', () => {
  const toasts = ref([])   // [{ id, message, type: 'info' | 'success' | 'warning' | 'error' }]

  function dismiss(id) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function push(message, type = 'info', timeout = type === 'error' ? 8000 : 4000) {
    const id = _nextId++
    toasts.value.push({ id, message, type })
    if (timeout > 0) setTimeout(() => dismiss(id), timeout)
    return id
  }

  return {
    toasts,
    dismiss,
    info:    msg => push(msg, 'info'),
    success: msg => push(msg, 'success'),
    warning: msg => push(msg, 'warning'),
    error:   msg => push(msg, 'error'),
  }
})
