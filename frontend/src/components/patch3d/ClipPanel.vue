<template>
  <div class="clip-panel">
    <div class="panel-header">
      <h3>Clip Points</h3>
      <label class="toggle-label" title="Enable/disable clip filter">
        <input type="checkbox" v-model="store.clipActive" @change="onToggle" />
        <span class="toggle-text">{{ store.clipActive ? 'On' : 'Off' }}</span>
      </label>
    </div>

    <div v-if="store.clipActive" class="axes">
      <!-- One block per axis. Hovering or dragging a slider shows its cut plane in the 3D view. -->
      <div v-for="ax in AXES" :key="ax.key" class="axis-section" :class="'ax-' + ax.key">
        <div class="axis-label">{{ ax.key }}</div>
        <div class="range-row">
          <input v-for="side in ['Min', 'Max']" :key="side"
            type="range" :min="store[ax.key + 'BoundsMin']" :max="store[ax.key + 'BoundsMax']" :step="step"
            v-model.number="store[ax.key + 'Clip' + side]" @input="onClipChange" class="range-input"
            :class="{ hot: isHover(ax.key, side) }"
            @pointerenter="hoverOn(ax.key, side)" @pointerleave="hoverOff(ax.key, side)"
            @pointerdown="dragging = { axis: ax.key, side }" @focus="hoverOn(ax.key, side)" @blur="hoverOff(ax.key, side, true)"
            :title="`${ax.key.toUpperCase()} ${side.toLowerCase()}: removes the ${ax[side]} side`" />
        </div>
        <div class="range-vals">
          <span>{{ fmt(store[ax.key + 'ClipMin'] + ax.offset()) }}</span>
          <span v-if="store.clipHover?.axis === ax.key" class="side-hint">
            cuts the {{ ax[store.clipHover.side] }} side
          </span>
          <span>{{ fmt(store[ax.key + 'ClipMax'] + ax.offset()) }}</span>
        </div>
      </div>

      <p v-if="clippedCount > 0" class="clip-count">
        {{ clippedCount.toLocaleString() }} points will be deleted
      </p>
      <p v-else class="clip-count faint">No points outside clip bounds</p>

      <div class="btn-row">
        <button class="reset-btn" @click="resetClip">Reset</button>
        <button
          class="delete-btn"
          :disabled="clippedCount === 0 || deleting"
          @click="$emit('delete-clipped')"
        >
          {{ deleting ? 'Deleting…' : 'Delete Clipped' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch, ref, onBeforeUnmount } from 'vue'
import { usePatch3DStore } from '../../stores/patch3d.js'

const props = defineProps({
  clippedCount: { type: Number, default: 0 },
  deleting:     { type: Boolean, default: false },
})
const emit = defineEmits(['clip-change', 'delete-clipped'])

const store = usePatch3DStore()

// Projected CRS: x = easting, y = northing
const AXES = [
  { key: 'x', Min: 'west',   Max: 'east',  offset: () => store.originX },
  { key: 'y', Min: 'south',  Max: 'north', offset: () => store.originY },
  { key: 'z', Min: 'bottom', Max: 'top',   offset: () => 0 },
]

// Which slider is hovered / dragged → store.clipHover → cut plane in the 3D view.
// While dragging, the plane stays even if the pointer leaves the slider.
const dragging = ref(null)
const isHover = (axis, side) => store.clipHover?.axis === axis && store.clipHover?.side === side
function hoverOn(axis, side) { store.clipHover = { axis, side } }
function hoverOff(axis, side, force = false) {
  if (!force && dragging.value) return
  if (isHover(axis, side)) store.clipHover = null
}
function endDrag() {
  if (!dragging.value) return
  dragging.value = null
  store.clipHover = null
}
window.addEventListener('pointerup', endDrag)
onBeforeUnmount(() => { window.removeEventListener('pointerup', endDrag); store.clipHover = null })

const step = computed(() => {
  const xRange = store.xBoundsMax - store.xBoundsMin
  const yRange = store.yBoundsMax - store.yBoundsMin
  const zRange = store.zBoundsMax - store.zBoundsMin
  const maxRange = Math.max(xRange, yRange, zRange, 1)
  // Round to a nice step — roughly 200 steps across the range
  const raw = maxRange / 200
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  return Math.max(0.01, Math.round(raw / mag) * mag)
})

function fmt(v) { return Number(v).toFixed(1) }

function onToggle() {
  if (!store.clipActive) {
    resetClip()
  } else {
    onClipChange()
  }
}

function onClipChange() {
  // Ensure lo <= hi
  if (store.xClipMin > store.xClipMax) store.xClipMin = store.xClipMax
  if (store.yClipMin > store.yClipMax) store.yClipMin = store.yClipMax
  if (store.zClipMin > store.zClipMax) store.zClipMin = store.zClipMax
  emit('clip-change')
}

function resetClip() {
  store.xClipMin = store.xBoundsMin; store.xClipMax = store.xBoundsMax
  store.yClipMin = store.yBoundsMin; store.yClipMax = store.yBoundsMax
  store.zClipMin = store.zBoundsMin; store.zClipMax = store.zBoundsMax
  emit('clip-change')
}

// When bounds are set (on patch load), initialise clip to full range
watch(() => store.xBoundsMax, () => {
  if (!store.clipActive) resetClip()
}, { immediate: true })
</script>

<style scoped>
.clip-panel { color: #eee; }
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px;
}
h3 { color: #adf; font-size: 14px; font-weight: 600; margin: 0; }
.toggle-label { display: flex; align-items: center; gap: 5px; cursor: pointer; font-size: 12px; color: #88a; }
.toggle-label input { accent-color: #7ab3ff; cursor: pointer; }

.axis-section { margin-bottom: 8px; }
.axis-label { font-size: 11px; font-weight: 600; color: #88a; margin-bottom: 3px; text-transform: uppercase; letter-spacing: 1px; }

.range-row { display: flex; flex-direction: column; gap: 12px; padding: 5px 0; }  /* thumbs must not overlap the other slider */
.range-input {
  width: 100%;
  -webkit-appearance: none;
  height: 4px;
  border-radius: 2px;
  background: #334;
  outline: none;
  cursor: pointer;
}
.range-input::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #7ab3ff;
  border: 2px solid #0d0d1f;
  cursor: pointer;
}
.range-input::-moz-range-thumb {
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #7ab3ff;
  border: 2px solid #0d0d1f;
  cursor: pointer;
}
.range-input:hover {
  background: #3a4a6a;
}
.range-input:hover::-webkit-slider-thumb {
  background: #b0d8ff;
  width: 18px; height: 18px;
  box-shadow: 0 0 0 4px rgba(122, 179, 255, 0.25);
}
.range-input:hover::-moz-range-thumb {
  background: #b0d8ff;
  width: 18px; height: 18px;
  box-shadow: 0 0 0 4px rgba(122, 179, 255, 0.25);
}

.range-vals {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: 10px; color: #667; font-family: monospace;
}
.side-hint { font-family: system-ui, sans-serif; font-size: 10.5px; font-weight: 600; }
/* axis colours match the cut plane in the 3D view */
.ax-x .side-hint, .ax-x .axis-label { color: #ff7a7a; }
.ax-y .side-hint, .ax-y .axis-label { color: #6ee07e; }
.ax-z .side-hint, .ax-z .axis-label { color: #78acff; }
.ax-x .range-input.hot::-webkit-slider-thumb { background: #ff7a7a; }
.ax-y .range-input.hot::-webkit-slider-thumb { background: #6ee07e; }
.ax-z .range-input.hot::-webkit-slider-thumb { background: #78acff; }
.ax-x .range-input.hot::-moz-range-thumb { background: #ff7a7a; }
.ax-y .range-input.hot::-moz-range-thumb { background: #6ee07e; }
.ax-z .range-input.hot::-moz-range-thumb { background: #78acff; }

.clip-count { font-size: 12px; color: #f99; margin: 6px 0; }
.faint { color: #556; }

.btn-row { display: flex; gap: 6px; margin-top: 6px; }
.reset-btn {
  flex: 1; padding: 7px;
  background: #2a2a4e; border: 1px solid #445;
  border-radius: 5px; color: #99b; cursor: pointer; font-size: 12px;
}
.reset-btn:hover { background: #3a3a6e; color: #ccf; }

.delete-btn {
  flex: 2; padding: 7px;
  background: #5a1a1a; border: 1px solid #884444;
  border-radius: 5px; color: #f99; cursor: pointer; font-size: 12px;
  font-weight: 600;
}
.delete-btn:hover:not(:disabled) { background: #6a2a2a; color: #fbb; }
.delete-btn:disabled { opacity: 0.4; cursor: default; }
</style>
