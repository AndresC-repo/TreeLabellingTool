<template>
  <div class="label-panel">
    <div class="panel-header">
      <h3>Label</h3>
      <button
        class="gear-btn"
        :class="{ active: settingsOpen }"
        @click="settingsOpen = !settingsOpen"
        title="Label settings"
      >⚙</button>
    </div>

    <!-- Settings drawer -->
    <div v-if="settingsOpen" class="settings-drawer">
      <label class="setting-row">
        <input type="checkbox" v-model="store.protectClasses" />
        <span>Skip ground &amp; buildings (class 2 / 6)</span>
      </label>
      <label class="setting-row">
        <input type="checkbox" v-model="store.showAllLabels" />
        <span>Show all labels (incl. ASPRS &lt;100)</span>
      </label>
      <label class="setting-row setting-row-inline">
        <span>Base Ground label</span>
        <input type="number" v-model.number="store.baseGround" min="0" max="99" class="base-ground-input" />
      </label>
    </div>

    <div class="label-control">
      <button class="step-btn" @click="decrement">−</button>
      <input v-model.number="labelValue" type="number" min="0" />
      <button class="step-btn" @click="increment">+</button>
    </div>
    <p class="hint" v-if="store.selectedIndices.length > 0">
      {{ store.selectedIndices.length.toLocaleString() }} points selected
      <span v-if="store.protectClasses" class="protect-note">(2/6 protected)</span>
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
      :title="`Label selection as ground (${store.baseGround}) [G]`"
    >
      Label GND ({{ store.baseGround }}) <kbd>G</kbd>
    </button>
    <p v-if="store.lassoProcessing" class="hint">Processing lasso selection...</p>

    <!-- Replace label X → Y within selection -->
    <div v-if="store.selectedIndices.length > 0" class="replace-section">
      <div class="replace-row">
        <span class="replace-lbl">Replace</span>
        <input v-model.number="fromLabel" type="number" min="0" class="replace-input" title="Source label" />
        <span class="replace-arrow">→</span>
        <input v-model.number="toLabel" type="number" min="0" class="replace-input" title="Target label" />
      </div>
      <button class="replace-btn" :disabled="applying" @click="applyReplace">
        {{ replacing ? 'Replacing...' : 'Replace in Selection' }}
      </button>
      <p v-if="replaceResult !== null" class="hint replace-result">{{ replaceResult }} pts replaced</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { usePatch3DStore } from '../../stores/patch3d.js'
import { useView2DStore } from '../../stores/view2d.js'
import { labelPoints, getNextLabel, relabelSelection } from '../../api/client.js'
import { useRoute } from 'vue-router'

const store = usePatch3DStore()
const view2d = useView2DStore()
const route = useRoute()
const labelValue = ref(store.nextLabel)
const applying = ref(false)
const replacing = ref(false)
const settingsOpen = ref(false)
const fromLabel = ref(0)
const toLabel = ref(101)
const replaceResult = ref(null)

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
      label_value: store.baseGround,
      protect_classes: store.protectClasses,
    })
    store.lastApplied = { indices: Array.from(store.selectedIndices), labelValue: store.baseGround, protectClasses: store.protectClasses }
    store.viewMode = 'classification'
    view2d.markLabelled(route.params.patchId)
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
      protect_classes: store.protectClasses,
    })
    store.lastApplied = { indices: Array.from(store.selectedIndices), labelValue: labelValue.value, protectClasses: store.protectClasses }
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

async function applyReplace() {
  if (store.selectedIndices.length === 0 || replacing.value) return
  replacing.value = true
  replaceResult.value = null
  try {
    const res = await relabelSelection(
      route.params.id,
      route.params.patchId,
      Array.from(store.selectedIndices),
      fromLabel.value,
      toLabel.value,
    )
    const { applied, applied_indices } = res.data
    replaceResult.value = applied
    if (applied > 0) {
      store.lastApplied = { indices: applied_indices, labelValue: toLabel.value, protectClasses: false }
      store.viewMode = 'classification'
      store.addAppliedLabel(toLabel.value)
      view2d.markLabelled(route.params.patchId)
    }
  } catch (err) {
    console.error('Replace label failed:', err)
    replaceResult.value = 'error'
  } finally {
    replacing.value = false
  }
}
</script>

<style scoped>
.label-panel { color: #eee; }

.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px;
}
h3 { color: #adf; font-size: 14px; font-weight: 600; margin: 0; }

.gear-btn {
  background: none; border: 1px solid transparent;
  color: #778; font-size: 15px; cursor: pointer;
  border-radius: 4px; padding: 2px 5px; line-height: 1;
  transition: color 0.15s, border-color 0.15s;
}
.gear-btn:hover  { color: #adf; border-color: #445; }
.gear-btn.active { color: #adf; border-color: #4a7aae; background: #1a2a3e; }

.settings-drawer {
  background: #131828; border: 1px solid #334;
  border-radius: 5px; padding: 8px 10px; margin-bottom: 10px;
}
.setting-row {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: #aac; cursor: pointer;
}
.setting-row input[type="checkbox"] { accent-color: #7ab3ff; cursor: pointer; }
.setting-row-inline { justify-content: space-between; margin-top: 6px; cursor: default; }
.base-ground-input {
  width: 52px; text-align: center;
  background: #1e2840; color: #eee;
  border: 1px solid #445; border-radius: 3px;
  padding: 2px 4px; font-size: 12px;
}

.label-control { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
input[type="number"] {
  width: 80px; text-align: center;
  background: #2a2a4e; color: #eee;
  border: 1px solid #556; padding: 6px;
  border-radius: 4px; font-size: 16px;
}
input[type="number"]::-webkit-inner-spin-button { opacity: 0.5; }
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
.protect-note { color: #668; font-size: 11px; }

.replace-section { margin-top: 10px; border-top: 1px solid #334; padding-top: 10px; }
.replace-row {
  display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
}
.replace-lbl { font-size: 12px; color: #88a; white-space: nowrap; }
.replace-arrow { font-size: 14px; color: #556; }
.replace-input {
  width: 52px; text-align: center;
  background: #2a2a4e; color: #eee;
  border: 1px solid #556; padding: 4px;
  border-radius: 4px; font-size: 13px;
}
.replace-input::-webkit-inner-spin-button { opacity: 0.5; }
.replace-btn {
  width: 100%; padding: 8px;
  background: #3a2a5e; border: 1px solid #6a5a8e;
  border-radius: 6px; color: #cca; cursor: pointer; font-size: 13px;
}
.replace-btn:hover:not(:disabled) { background: #4a3a7e; }
.replace-btn:disabled { opacity: 0.4; cursor: default; }
.replace-result { color: #adf; }

kbd {
  display: inline-block; font-size: 9px; font-family: monospace;
  background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
  border-radius: 3px; padding: 0 3px; margin-left: 4px;
  line-height: 1.6; color: #99b; vertical-align: middle;
}
</style>
