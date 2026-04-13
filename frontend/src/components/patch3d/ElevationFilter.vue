<template>
  <div class="elev-filter" v-show="visible">
    <div class="filter-title">Z filter</div>

    <!-- Main body: action buttons on left, track on right -->
    <div class="filter-body">

      <!-- Left column: action buttons that follow the thumbs -->
      <div class="btn-col" :style="{ height: TRACK_H + 'px' }">
        <button
          class="action-btn label-btn"
          :style="{ top: hiPct + '%' }"
          :title="`Label ${labelValue} — all points inside the Z range`"
          @click="$emit('label-inside')"
        >
          +{{ labelValue }}
        </button>
        <button
          class="action-btn gnd-btn"
          :style="{ top: loPct + '%' }"
          title="GND — label all points below the lower bound as 0"
          @click="$emit('gnd-below')"
        >
          GND+
        </button>
      </div>

      <!-- Right column: the slider track -->
      <div class="track-wrap" ref="trackEl" :style="{ height: TRACK_H + 'px' }">
        <div class="track-bg"></div>
        <div class="track-active" :style="activeStyle"></div>

        <!-- Hi thumb — controls upper Z cutoff -->
        <div
          class="thumb thumb-hi"
          :style="{ top: hiPct + '%' }"
          @pointerdown.prevent="startDrag('hi', $event)"
        >
          <span class="z-val">{{ hiZ.toFixed(1) }}</span>
        </div>

        <!-- Lo thumb — controls lower Z cutoff -->
        <div
          class="thumb thumb-lo"
          :style="{ top: loPct + '%' }"
          @pointerdown.prevent="startDrag('lo', $event)"
        >
          <span class="z-val">{{ loZ.toFixed(1) }}</span>
        </div>
      </div>
    </div>

    <button class="reset-btn" @click="resetFilter" title="Reset Z filter">↺</button>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'

const TRACK_H = 180

const props = defineProps({
  visible:        { type: Boolean, default: true },
  zMin:           { type: Number,  default: 0 },
  zMax:           { type: Number,  default: 100 },
  modelValueLo:   { type: Number,  default: null },
  modelValueHi:   { type: Number,  default: null },
  labelValue:     { type: Number,  default: 101 },
})
const emit = defineEmits([
  'update:modelValueLo',
  'update:modelValueHi',
  'label-inside',
  'gnd-below',
])

const trackEl = ref(null)
const loZ = ref(props.zMin)
const hiZ = ref(props.zMax)

// Sync when a new patch is loaded (zMin/zMax change)
watch(() => [props.zMin, props.zMax], ([min, max]) => {
  loZ.value = min; hiZ.value = max
  emit('update:modelValueLo', min)
  emit('update:modelValueHi', max)
})

// Track top = zMax (0 %), track bottom = zMin (100 %)
function zToPct(z) {
  const range = props.zMax - props.zMin
  if (range < 1e-6) return 0
  return (1 - (z - props.zMin) / range) * 100
}
function pctToZ(pct) {
  return props.zMax - (pct / 100) * (props.zMax - props.zMin)
}

const hiPct = computed(() => zToPct(hiZ.value))
const loPct = computed(() => zToPct(loZ.value))

const activeStyle = computed(() => ({
  top:    hiPct.value + '%',
  height: Math.max(0, loPct.value - hiPct.value) + '%',
}))

// ── Drag ──────────────────────────────────────────────────────────────────────
let dragging = null
let trackRect = null
let dragOffsetY = 0

function startDrag(which, e) {
  dragging = which
  trackRect = trackEl.value.getBoundingClientRect()
  const thumbRect = e.currentTarget.getBoundingClientRect()
  dragOffsetY = e.clientY - (thumbRect.top + thumbRect.height / 2)
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
  e.currentTarget.setPointerCapture(e.pointerId)
}

function onDragMove(e) {
  if (!dragging || !trackRect) return
  const pct = Math.min(100, Math.max(0,
    (e.clientY - dragOffsetY - trackRect.top) / trackRect.height * 100
  ))
  const z = pctToZ(pct)
  if (dragging === 'hi') {
    hiZ.value = Math.min(Math.max(z, loZ.value), props.zMax)
    emit('update:modelValueHi', hiZ.value)
  } else {
    loZ.value = Math.max(Math.min(z, hiZ.value), props.zMin)
    emit('update:modelValueLo', loZ.value)
  }
}

function onDragEnd() {
  dragging = null
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
}

function resetFilter() {
  loZ.value = props.zMin; hiZ.value = props.zMax
  emit('update:modelValueLo', props.zMin)
  emit('update:modelValueHi', props.zMax)
}

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
})
</script>

<style scoped>
.elev-filter {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  z-index: 10;
  pointer-events: all;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 10px;
  padding: 8px 8px 6px;
}

.filter-title {
  font-size: 10px;
  color: #88a;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.filter-body {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

/* ── Button column ─────────────────────────────────────────────── */
.btn-col {
  position: relative;
  width: 48px;
}

.action-btn {
  position: absolute;
  transform: translateY(-50%);
  right: 0;
  width: 46px;
  padding: 3px 4px;
  font-size: 10px;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
  text-align: center;
  line-height: 1.3;
  border: 1px solid;
  transition: background 0.15s;
}

.label-btn {
  background: #1e3050;
  border-color: #4a7abf;
  color: #8bc;
}
.label-btn:hover { background: #2a4070; color: #adf; }

.gnd-btn {
  background: #1e3a2a;
  border-color: #3a6a4a;
  color: #6da;
}
.gnd-btn:hover { background: #2a4a36; color: #8ec; }

/* ── Track column ──────────────────────────────────────────────── */
.track-wrap {
  position: relative;
  width: 14px;
}

.track-bg {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: 4px;
  height: 100%;
  background: #334;
  border-radius: 2px;
}

.track-active {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: 4px;
  background: #5af;
  border-radius: 2px;
}

.thumb {
  position: absolute;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #5af;
  border: 2px solid #fff;
  cursor: grab;
  z-index: 1;
}
.thumb:active { cursor: grabbing; }

.z-val {
  position: absolute;
  left: 18px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 10px;
  color: #cde;
  white-space: nowrap;
  pointer-events: none;
  background: rgba(0,0,0,0.65);
  padding: 1px 4px;
  border-radius: 3px;
}

/* ── Reset button ──────────────────────────────────────────────── */
.reset-btn {
  background: none;
  border: 1px solid #446;
  color: #88a;
  border-radius: 4px;
  width: 22px;
  height: 22px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.reset-btn:hover { color: #adf; border-color: #7af; }
</style>
