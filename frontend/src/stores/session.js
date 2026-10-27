import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { getSessionInfo } from '../api/client.js'

const STORAGE_KEY = 'labelling-tool.sessions.v1'

function loadSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list.filter(s => s && s.sessionId) : []
  } catch {
    return []
  }
}

export const useSessionStore = defineStore('session', () => {
  // Current active session (drives API calls / toolbar display)
  const sessionId = ref(null)
  const filename = ref(null)
  const pointCount = ref(0)
  const bounds = ref(null)
  const availableFields = ref([])

  // All loaded sessions — persisted in localStorage so a page reload keeps the list
  const sessions = ref(loadSaved())   // [{ sessionId, filename, pointCount, bounds, availableFields }]

  watch(sessions, list => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(list)) } catch { /* storage unavailable */ }
  }, { deep: true })

  function _toEntry(data) {
    return {
      sessionId: data.session_id,
      filename: data.filename,
      pointCount: data.point_count,
      bounds: data.bounds,
      availableFields: data.available_fields,
      units: data.units ?? null,   // { code, name, scale, source: crs|guess|uncertain|default|user }
    }
  }

  function _upsert(entry) {
    const idx = sessions.value.findIndex(s => s.sessionId === entry.sessionId)
    if (idx === -1) sessions.value.push(entry)
    else sessions.value[idx] = entry
  }

  /** Upload result → set as current AND add to list */
  function setSession(data) {
    const entry = _toEntry(data)
    _upsert(entry)
    switchTo(entry)
  }

  /** Add to list without changing the active session */
  function addSession(data) {
    _upsert(_toEntry(data))
  }

  /** Switch current to an already-loaded session entry */
  function switchTo(entry) {
    sessionId.value = entry.sessionId
    filename.value = entry.filename
    pointCount.value = entry.pointCount
    bounds.value = entry.bounds
    availableFields.value = entry.availableFields
  }

  /** Remove a session from the list; if it was active, switch to the first remaining one */
  function removeSession(id) {
    sessions.value = sessions.value.filter(s => s.sessionId !== id)
    if (sessionId.value === id) {
      const next = sessions.value[0] ?? null
      if (next) switchTo(next)
      else { sessionId.value = null; filename.value = null }
    }
  }

  /**
   * Check the saved list against the server once per page load and drop files
   * the server no longer has (deleted, or removed by the idle cleanup).
   * Resolves to the number of entries dropped.
   */
  let _initPromise = null
  function init() {
    if (!_initPromise) {
      _initPromise = Promise.all(sessions.value.map(async s => {
        try {
          const res = await getSessionInfo(s.sessionId)
          return { id: s.sessionId, entry: _toEntry(res.data) }
        } catch (err) {
          // Only a definite "not found" removes an entry; a backend that is down keeps the list
          return { id: s.sessionId, gone: err.response?.status === 404 }
        }
      })).then(results => {
        let dropped = 0
        for (const r of results) {
          if (r.entry) _upsert(r.entry)
          else if (r.gone) { removeSession(r.id); dropped++ }
        }
        return dropped
      })
    }
    return _initPromise
  }

  /** Make sure a session id (e.g. from the URL) is in the list. Returns the entry or null. */
  async function ensure(id) {
    const existing = sessions.value.find(s => s.sessionId === id)
    if (existing) return existing
    try {
      const res = await getSessionInfo(id)
      addSession(res.data)
      return sessions.value.find(s => s.sessionId === id) ?? null
    } catch {
      return null
    }
  }

  return {
    sessionId, filename, pointCount, bounds, availableFields, sessions,
    setSession, addSession, switchTo, removeSession, init, ensure,
  }
})
