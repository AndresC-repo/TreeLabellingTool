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
      <!-- X axis -->
      <div class="axis-section">
        <div class="axis-label">X</div>
        <div class="range-row">
          <input type="range" :min="store.xBoundsMin" :max="store.xBoundsMax" :step="step"
            v-model.number="store.xClipMin" @input="onClipChange" class="range-input" />
          <input type="range" :min="store.xBoundsMin" :max="store.xBoundsMax" :step="step"
            v-model.number="store.xClipMax" @input="onClipChange" class="range-input" />
        </div>
        <div class="range-vals">
          <span>{{ fmt(store.xClipMin) }}</span>
          <span>{{ fmt(store.xClipMax) }}</span>
        </div>
      </div>

      <!-- Y axis -->
      <div class="axis-section">
        <div class="axis-label">Y</div>
        <div class="range-row">
          <input type="range" :min="store.yBoundsMin" :max="store.yBoundsMax" :step="step"
            v-model.number="store.yClipMin" @input="onClipChange" class="range-input" />
          <input type="range" :min="store.yBoundsMin" :max="store.yBoundsMax" :step="step"
            v-model.number="store.yClipMax" @input="onClipChange" class="range-input" />
        </div>
        <div class="range-vals">
          <span>{{ fmt(store.yClipMin) }}</span>
          <span>{{ fmt(store.yClipMax) }}</span>
        </div>
      </div>

      <!-- Z axis -->
      <div class="axis-section">
        <div class="axis-label">Z</div>
        <div class="range-row">
          <input type="range" :min="store.zBoundsMin" :max="store.zBoundsMax" :step="step"
            v-model.number="store.zClipMin" @input="onClipChange" class="range-input" />
          <input type="range" :min="store.zBoundsMin" :max="store.zBoundsMax" :step="step"
            v-model.number="store.zClipMax" @input="onClipChange" class="range-input" />
        </div>
        <div class="range-vals">
          <span>{{ fmt(store.zClipMin) }}</span>
          <span>{{ fmt(store.zClipMax) }}</span>
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
import { computed, watch } from 'vue'
import { usePatch3DStore } from '../../stores/patch3d.js'

const props = defineProps({
  clippedCount: { type: Number, default: 0 },
  deleting:     { type: Boolean, default: false },
})
const emit = defineEmits(['clip-change', 'delete-clipped'])

const store = usePatch3DStore()

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

.range-row { display: flex; flex-direction: column; gap: 3px; }
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

.range-vals {
  display: flex; justify-content: space-between;
  font-size: 10px; color: #667; font-family: monospace;
}

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
