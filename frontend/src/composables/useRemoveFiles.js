// Deleting loaded files (one, several, or a whole folder) with a confirmation that
// shows how many patches go with them. Shared by the start page and the 2D view.
import { ref } from 'vue'
import { deleteSession, getSessionInfo } from '../api/client.js'
import { useSessionStore } from '../stores/session.js'
import { useToastStore } from '../stores/toast.js'

/**
 * @param {object} opts
 * @param {(ids: string[]) => void} [opts.onRemoved]  after entries left the list
 * @param {() => void} [opts.onAsk]                    before the confirmation opens
 */
export function useRemoveFiles({ onRemoved, onAsk } = {}) {
  const session = useSessionStore()
  const toast = useToastStore()
  const removing = ref(false)
  const pendingRemove = ref(null)   // { entries, patchCount, counts: { [sessionId]: n }, folder }

  function finish(ids) {
    for (const id of ids) session.removeSession(id)
    onRemoved?.(ids)
  }

  async function requestRemove(entries, folder = null) {
    if (removing.value || !entries.length) return
    removing.value = true
    const counts = {}
    const alreadyGone = []
    await Promise.all(entries.map(async e => {
      try {
        counts[e.sessionId] = (await getSessionInfo(e.sessionId)).data.patch_count ?? 0
      } catch (err) {
        if (err.response?.status === 404) alreadyGone.push(e)
        else counts[e.sessionId] = 1   // can't tell (backend unreachable) → make the user confirm
      }
    }))
    removing.value = false

    if (alreadyGone.length) {
      finish(alreadyGone.map(e => e.sessionId))
      toast.info(`${alreadyGone.map(e => e.filename).join(', ')} ${alreadyGone.length === 1 ? 'was' : 'were'} already removed from the server.`)
    }
    const remaining = entries.filter(e => e.sessionId in counts)
    if (!remaining.length) return

    const patchCount = remaining.reduce((n, e) => n + counts[e.sessionId], 0)
    // Deleting several files always asks, so a stray click can't wipe the list
    if (patchCount > 0 || remaining.length > 1) {
      onAsk?.()
      pendingRemove.value = { entries: remaining, patchCount, counts, folder }
    } else {
      await deleteEntries(remaining, folder)
    }
  }

  async function confirmRemove() {
    const { entries, folder } = pendingRemove.value
    pendingRemove.value = null
    await deleteEntries(entries, folder)
  }

  async function deleteEntries(entries, folder = null) {
    removing.value = true
    const results = await Promise.allSettled(entries.map(e => deleteSession(e.sessionId)))
    removing.value = false
    const done = [], failed = []
    results.forEach((r, i) => {
      // 404 = already gone on the server → still remove locally
      if (r.status === 'fulfilled' || r.reason?.response?.status === 404) done.push(entries[i])
      else failed.push(`${entries[i].filename} (${r.reason?.response?.data?.detail || r.reason?.message || 'unknown error'})`)
    })
    if (done.length) {
      finish(done.map(e => e.sessionId))
      toast.info(folder && done.length === entries.length ? `Deleted folder ${folder} (${done.length} file${done.length === 1 ? '' : 's'}).`
        : done.length === 1 ? `Deleted ${done[0].filename}.` : `Deleted ${done.length} files.`)
    }
    if (failed.length) toast.error(`Could not delete: ${failed.join(', ')}`)
  }

  return { removing, pendingRemove, requestRemove, confirmRemove, deleteEntries }
}
