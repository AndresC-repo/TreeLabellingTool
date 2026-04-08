import * as THREE from 'three'
import { ref, reactive } from 'vue'

/**
 * Fixed rectangle tool.
 * Draw once; then drag the whole rectangle to reposition it.
 * Emits a bounds object each time the rectangle is released.
 */
export function useFixedRect(camera, rendererDomEl) {
  const hasRect = ref(false)
  const svgRect = reactive({ x1: 0, y1: 0, x2: 0, y2: 0 })

  let drawing = false
  let dragging = false
  let dragStart = { x: 0, y: 0, rx1: 0, ry1: 0, rx2: 0, ry2: 0 }

  function screenToWorld(clientX, clientY) {
    const el = rendererDomEl.value
    const r = el.getBoundingClientRect()
    const ndcX = ((clientX - r.left) / r.width)  * 2 - 1
    const ndcY = -((clientY - r.top)  / r.height) * 2 + 1
    const vec = new THREE.Vector3(ndcX, ndcY, 0)
    vec.unproject(camera.value)
    return { x: vec.x, y: vec.y }
  }

  function getWorldBounds(e) {
    const el = rendererDomEl.value
    const r = el.getBoundingClientRect()
    const w1 = screenToWorld(svgRect.x1 + r.left, svgRect.y1 + r.top)
    const w2 = screenToWorld(svgRect.x2 + r.left, svgRect.y2 + r.top)
    return {
      x_min: Math.min(w1.x, w2.x),
      x_max: Math.max(w1.x, w2.x),
      y_min: Math.min(w1.y, w2.y),
      y_max: Math.max(w1.y, w2.y),
    }
  }

  function onMouseDown(e) {
    if (e.button !== 0) return
    if (!hasRect.value) {
      drawing = true
      svgRect.x1 = e.offsetX
      svgRect.y1 = e.offsetY
      svgRect.x2 = e.offsetX
      svgRect.y2 = e.offsetY
    } else {
      dragging = true
      dragStart = { x: e.offsetX, y: e.offsetY, rx1: svgRect.x1, ry1: svgRect.y1, rx2: svgRect.x2, ry2: svgRect.y2 }
    }
  }

  function onMouseMove(e) {
    if (drawing) {
      svgRect.x2 = e.offsetX
      svgRect.y2 = e.offsetY
    } else if (dragging) {
      const dx = e.offsetX - dragStart.x
      const dy = e.offsetY - dragStart.y
      svgRect.x1 = dragStart.rx1 + dx
      svgRect.y1 = dragStart.ry1 + dy
      svgRect.x2 = dragStart.rx2 + dx
      svgRect.y2 = dragStart.ry2 + dy
    }
  }

  /**
   * @returns {{ x_min, x_max, y_min, y_max } | null}
   */
  function onMouseUp(e) {
    let bounds = null
    if (drawing) {
      drawing = false
      svgRect.x2 = e.offsetX
      svgRect.y2 = e.offsetY
      if (Math.abs(svgRect.x2 - svgRect.x1) > 3 && Math.abs(svgRect.y2 - svgRect.y1) > 3) {
        hasRect.value = true
        bounds = getWorldBounds(e)
      }
    } else if (dragging) {
      dragging = false
      bounds = getWorldBounds(e)
    }
    return bounds
  }

  function reset() {
    hasRect.value = false
    dragging = false
    drawing = false
  }

  return { hasRect, svgRect, onMouseDown, onMouseMove, onMouseUp, reset, getWorldBounds }
}
