<template>
  <div class="label-panel">
    <h3>Label</h3>
    <div class="label-control">
      <button class="step-btn" @click="decrement">−</button>
      <input v-model.number="labelValue" type="number" min="0" />
      <button class="step-btn" @click="increment">+</button>
    </div>
    <p class="hint" v-if="store.selectedIndices.length > 0">
      {{ store.selectedIndices.length.toLocaleString() }} points selected
    </p>
    <p class="hint faint" v-else-if="!store.lassoProcessing">Draw a lasso to select points</p>
    <button
      class="apply-btn"
      :disabled="store.selectedIndices.length === 0 || applying"
      @click="applyLabel"
      title="Apply label [Enter]"
    >
      {{ applying ? 'Applying...' : `Apply Label ${labelValue}` }} <kbd>↵</kbd> <kbd>Space</kbd>
    </button>
    <button
      class="gnd-btn"
      :disabled="store.selectedIndices.length === 0 || applying"
      @click="applyGnd"
      title="Label as ground (0) [G]"
    >
      Label GND (0) <kbd>G</kbd>
    </button>
    <p v-if="store.lassoProcessing" class="hint">Processing lasso selection...</p>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useView2DStore } from '../../stores/view2d.js'
import { labelPoints, getNextLabel } from '../../api/client.js'
import { useRoute } from 'vue-router'

const store = usePatch3DStore()
const view2d = useView2DStore()
const route = useRoute()
const labelValue = ref(store.nextLabel)
const applying = ref(false)

// Keep in sync with store (lasso updates store.nextLabel after each apply)
watch(() => store.nextLabel, v => { labelValue.value = v })

function increment() { labelValue.value++ }
function decrement() { labelValue.value = Math.max(0, labelValue.value - 1) }

defineExpose({ applyLabel, applyGnd })

async function applyGnd() {
  if (store.selectedIndices.length === 0) return
  applying.value = true
  try {
    await labelPoints(route.params.id, route.params.patchId, {
      point_indices: Array.from(store.selectedIndices),
      label_value: 0,
    })
    store.lastApplied = { indices: Array.from(store.selectedIndices), labelValue: 0 }
    store.viewMode = 'classification'
    view2d.markLabelled(route.params.patchId)
    // 0 is intentionally not added to appliedLabels (excluded from filename)
    store.selectedIndices = []
  } catch (err) {
    console.error('GND label failed:', err)
  } finally {
    applying.value = false
  }
}

async function applyLabel() {
  if (store.selectedIndices.length === 0) return
  applying.value = true
  try {
    await labelPoints(route.params.id, route.params.patchId, {
      point_indices: Array.from(store.selectedIndices),
      label_value: labelValue.value,
    })
    // Signal the canvas to recolor + switch view before clearing selection
    store.lastApplied = { indices: Array.from(store.selectedIndices), labelValue: labelValue.value }
    store.viewMode = 'classification'
    store.addAppliedLabel(labelValue.value)
    view2d.markLabelled(route.params.patchId)
    const res = await getNextLabel(route.params.id, route.params.patchId)
    store.nextLabel = res.data.next_label
    store.selectedIndices = []
    labelValue.value = store.nextLabel
  } catch (err) {
    console.error('Label apply failed:', err)
  } finally {
    applying.value = false
  }
}

</script>

<style scoped>
.label-panel { color: #eee; }
h3 { color: #adf; margin-bottom: 12px; font-size: 14px; font-weight: 600; }
.label-control { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
input {
  width: 80px; text-align: center;
  background: #2a2a4e; color: #eee;
  border: 1px solid #556; padding: 6px;
  border-radius: 4px; font-size: 16px;
}
input::-webkit-inner-spin-button { opacity: 0.5; }
.step-btn {
  background: #2a2a4e; color: #eee;
  border: 1px solid #445;
  width: 32px; height: 32px;
  border-radius: 4px; cursor: pointer; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
}
.step-btn:hover { background: #3a3a6e; }
.apply-btn {
  width: 100%; padding: 10px;
  background: #2a5a8e; border: none;
  border-radius: 6px; color: #eee; cursor: pointer; font-size: 14px;
}
.apply-btn:hover:not(:disabled) { background: #3a6aae; }
.apply-btn:disabled { opacity: 0.4; cursor: default; }
.gnd-btn {
  width: 100%; padding: 8px;
  background: #3a3a3a; border: 1px solid #555;
  border-radius: 6px; color: #aaa; cursor: pointer; font-size: 13px;
  margin-top: 6px;
}
.gnd-btn:hover:not(:disabled) { background: #4a4a4a; color: #ccc; }
.gnd-btn:disabled { opacity: 0.4; cursor: default; }
.hint { font-size: 12px; color: #88a; margin-bottom: 8px; }
.faint { color: #556; }
kbd {
  display: inline-block; font-size: 9px; font-family: monospace;
  background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
  border-radius: 3px; padding: 0 3px; margin-left: 4px;
  line-height: 1.6; color: #99b; vertical-align: middle;
}
</style>
