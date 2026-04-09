import * as THREE from 'three'
import { onMounted, onBeforeUnmount, shallowRef } from 'vue'

export function useThreeScene(containerRef, cameraType = 'orthographic') {
  const renderer = shallowRef(null)
  const scene = shallowRef(null)
  const camera = shallowRef(null)
  let animFrameId = null
  let resizeObserver = null

  function init() {
    const el = containerRef.value
    const w = el.clientWidth
    const h = el.clientHeight

    renderer.value = new THREE.WebGLRenderer({ antialias: false })
    renderer.value.setPixelRatio(window.devicePixelRatio)
    renderer.value.setSize(w, h)
    el.appendChild(renderer.value.domElement)

    scene.value = new THREE.Scene()
    scene.value.background = new THREE.Color(0x1a1a2e)

    if (cameraType === 'orthographic') {
      camera.value = new THREE.OrthographicCamera(-w / 2, w / 2, h / 2, -h / 2, 0.1, 100000)
      camera.value.position.z = 100
    } else {
      camera.value = new THREE.PerspectiveCamera(60, w / h, 0.1, 1000000)
      camera.value.position.set(0, 0, 100)
    }

    function animate() {
      animFrameId = requestAnimationFrame(animate)
      renderer.value.render(scene.value, camera.value)
    }
    animate()

    resizeObserver = new ResizeObserver(() => {
      const w2 = el.clientWidth
      const h2 = el.clientHeight
      renderer.value.setSize(w2, h2)
      if (cameraType === 'orthographic') {
        camera.value.left   = -w2 / 2
        camera.value.right  =  w2 / 2
        camera.value.top    =  h2 / 2
        camera.value.bottom = -h2 / 2
        camera.value.updateProjectionMatrix()
      } else {
        camera.value.aspect = w2 / h2
        camera.value.updateProjectionMatrix()
      }
    })
    resizeObserver.observe(el)
  }

  onMounted(init)

  onBeforeUnmount(() => {
    if (animFrameId !== null) cancelAnimationFrame(animFrameId)
    resizeObserver?.disconnect()
    renderer.value?.dispose()
  })

  return { renderer, scene, camera }
}
