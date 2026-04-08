import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSessionStore = defineStore('session', () => {
  const sessionId = ref(null)
  const filename = ref(null)
  const pointCount = ref(0)
  const bounds = ref(null)
  const availableFields = ref([])

  function setSession(data) {
    sessionId.value = data.session_id
    filename.value = data.filename
    pointCount.value = data.point_count
    bounds.value = data.bounds
    availableFields.value = data.available_fields
  }

  return { sessionId, filename, pointCount, bounds, availableFields, setSession }
})
