import * as THREE from 'three'
import { ref, reactive } from 'vue'

/**
 * Rectangle selection tool.
 * Returns screen-space SVG coords for drawing and world-space bounds for the API.
 *
 * @param {import('vue').Ref} camera — THREE.OrthographicCamera ref
 * @param {import('vue').Ref} rendererDomEl — ref to the THREE.js canvas element
 */
export function useSelectionRect(camera, rendererDomEl) {
  const selecting = ref(false)
  const svgRect = reactive({ x1: 0, y1: 0, x2: 0, y2: 0 })

  let startClient = { x: 0, y: 0 }

  function screenToWorld(clientX, clientY) {
    const el = rendererDomEl.value
    const r = el.getBoundingClientRect()
    const ndcX = ((clientX - r.left) / r.width)  * 2 - 1
    const ndcY = -((clientY - r.top)  / r.height) * 2 + 1
    const vec = new THREE.Vector3(ndcX, ndcY, 0)
    vec.unproject(camera.value)
    return { x: vec.x, y: vec.y }
  }

  function onMouseDown(e) {
    if (e.button !== 0) return
    selecting.value = true
    startClient = { x: e.clientX, y: e.clientY }
    svgRect.x1 = e.offsetX
    svgRect.y1 = e.offsetY
    svgRect.x2 = e.offsetX
    svgRect.y2 = e.offsetY
  }

  function onMouseMove(e) {
    if (!selecting.value) return
    svgRect.x2 = e.offsetX
    svgRect.y2 = e.offsetY
  }

  /**
   * @returns {{ x_min, x_max, y_min, y_max } | null} world-space bounds or null if too small
   */
  function onMouseUp(e) {
    if (!selecting.value) return null
    selecting.value = false
    const w1 = screenToWorld(startClient.x, startClient.y)
    const w2 = screenToWorld(e.clientX, e.clientY)
    if (Math.abs(w1.x - w2.x) < 0.001 && Math.abs(w1.y - w2.y) < 0.001) return null
    return {
      x_min: Math.min(w1.x, w2.x),
      x_max: Math.max(w1.x, w2.x),
      y_min: Math.min(w1.y, w2.y),
      y_max: Math.max(w1.y, w2.y),
    }
  }

  return { selecting, svgRect, onMouseDown, onMouseMove, onMouseUp, screenToWorld }
}
