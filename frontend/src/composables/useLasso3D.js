import * as THREE from 'three'
import { ref } from 'vue'
import PIPWorker from '../workers/pointInPolygon.worker.js?worker'

export function useLasso3D(camera, renderer) {
  const drawing = ref(false)
  const lassoPoints = ref([]) // screen-space {x, y}
  const processing = ref(false)

  function addVertex(e) {
    lassoPoints.value = [...lassoPoints.value, { x: e.offsetX, y: e.offsetY }]
    drawing.value = true
  }

  function cancelLasso() {
    drawing.value = false
    lassoPoints.value = []
  }

  function finishLasso(positions) {
    if (!drawing.value || lassoPoints.value.length < 3) {
      cancelLasso()
      return Promise.resolve([])
    }
    drawing.value = false
    processing.value = true

    const el = renderer.value.domElement
    const mvp = new THREE.Matrix4()
    mvp.multiplyMatrices(camera.value.projectionMatrix, camera.value.matrixWorldInverse)
    const mvpArr = new Float32Array(mvp.elements)
    const polygon = lassoPoints.value.slice()
    lassoPoints.value = []

    return new Promise((resolve) => {
      const worker = new PIPWorker()
      worker.onmessage = (ev) => {
        processing.value = false
        resolve(Array.from(ev.data.indices))
        worker.terminate()
      }
      worker.onerror = (err) => {
        processing.value = false
        console.error('PIP worker error:', err)
        resolve([])
        worker.terminate()
      }
      worker.postMessage({
        positions,
        mvpMatrix: mvpArr,
        screenW: el.clientWidth,
        screenH: el.clientHeight,
        polygon,
      })
    })
  }

  return { drawing, lassoPoints, processing, addVertex, cancelLasso, finishLasso }
}
