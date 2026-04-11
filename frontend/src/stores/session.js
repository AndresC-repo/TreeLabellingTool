import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSessionStore = defineStore('session', () => {
  // Current active session (drives API calls / toolbar display)
  const sessionId = ref(null)
  const filename = ref(null)
  const pointCount = ref(0)
  const bounds = ref(null)
  const availableFields = ref([])

  // All loaded sessions across this browser session
  const sessions = ref([])   // [{ sessionId, filename, pointCount, bounds, availableFields }]

  function _toEntry(data) {
    return {
      sessionId: data.session_id,
      filename: data.filename,
      pointCount: data.point_count,
      bounds: data.bounds,
      availableFields: data.available_fields,
    }
  }

  /** Upload result → set as current AND add to list */
  function setSession(data) {
    const entry = _toEntry(data)
    const idx = sessions.value.findIndex(s => s.sessionId === entry.sessionId)
    if (idx === -1) sessions.value.push(entry)
    else sessions.value[idx] = entry
    sessionId.value = entry.sessionId
    filename.value = entry.filename
    pointCount.value = entry.pointCount
    bounds.value = entry.bounds
    availableFields.value = entry.availableFields
  }

  /** Add to list without changing the active session (used when loading extra files from View2D) */
  function addSession(data) {
    const entry = _toEntry(data)
    const idx = sessions.value.findIndex(s => s.sessionId === entry.sessionId)
    if (idx === -1) sessions.value.push(entry)
    else sessions.value[idx] = entry
  }

  /** Switch current to an already-loaded session entry */
  function switchTo(entry) {
    sessionId.value = entry.sessionId
    filename.value = entry.filename
    pointCount.value = entry.pointCount
    bounds.value = entry.bounds
    availableFields.value = entry.availableFields
  }

  /** Remove a session from the list; returns the entry to switch to (or null if list is now empty) */
  function removeSession(id) {
    sessions.value = sessions.value.filter(s => s.sessionId !== id)
    // If we removed the active session, switch to the first remaining one
    if (sessionId.value === id) {
      const next = sessions.value[0] ?? null
      if (next) switchTo(next)
      else { sessionId.value = null; filename.value = null }
    }
  }

  return { sessionId, filename, pointCount, bounds, availableFields, sessions, setSession, addSession, switchTo, removeSession }
})
