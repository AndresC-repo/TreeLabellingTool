import { ref, reactive } from 'vue'

/**
 * Rectangle selection tool.
 * @param {Function} toWorld  — (clientX, clientY) => { x, y } in world coordinates
 * @param {import('vue').Ref} domEl — ref to the canvas element
 */
export function useSelectionRect(toWorld, domEl) {
  const selecting = ref(false)
  const svgRect = reactive({ x1: 0, y1: 0, x2: 0, y2: 0 })
  let startClient = { x: 0, y: 0 }

  function onMouseDown(e) {
    if (e.button !== 0) return
    selecting.value = true
    startClient = { x: e.clientX, y: e.clientY }
    svgRect.x1 = e.offsetX; svgRect.y1 = e.offsetY
    svgRect.x2 = e.offsetX; svgRect.y2 = e.offsetY
  }

  function onMouseMove(e) {
    if (!selecting.value) return
    svgRect.x2 = e.offsetX
    svgRect.y2 = e.offsetY
  }

  function onMouseUp(e) {
    if (!selecting.value) return null
    selecting.value = false
    const w1 = toWorld(startClient.x, startClient.y)
    const w2 = toWorld(e.clientX, e.clientY)
    if (Math.abs(w1.x - w2.x) < 0.001 && Math.abs(w1.y - w2.y) < 0.001) return null
    return {
      x_min: Math.min(w1.x, w2.x), x_max: Math.max(w1.x, w2.x),
      y_min: Math.min(w1.y, w2.y), y_max: Math.max(w1.y, w2.y),
    }
  }

  return { selecting, svgRect, onMouseDown, onMouseMove, onMouseUp }
}
