<template>
  <div class="naip-panel">
    <div class="panel-header">
      <h3>🛰 NAIP</h3>
      <span class="state" :class="{ on: naip.status.running }"
            :title="naip.status.running ? 'NAIP service running' : 'Start the tool with “make naip” to use this'">
        {{ naip.status.running ? (naip.status.model ? 'ready' : 'image only') : 'off' }}
      </span>
    </div>

    <p v-if="!naip.status.running" class="dim small">
      Aerial image, image-model trees and true labels (USA only). Start the tool with
      <code>make naip</code> to use it.
    </p>

    <template v-else>
      <div class="row">
        <button class="run-btn" :disabled="loading" @click="load"
                :title="scope === 'tile' ? 'Fetch the image for the whole file and run the Ventura model on it (a large file can take a minute or two)' : 'Fetch the image for this patch and run the Ventura model on it'">
          {{ loading ? (scope === 'tile' ? 'Working on the whole file…' : 'Fetching image…') : (result ? 'Reload' : 'Load NAIP layers') }}
        </button>
        <select v-if="result?.years?.length > 1" v-model.number="year" class="sel" @change="load"
                title="Image year; pick the one closest to the lidar survey">
          <option v-for="y in result.years" :key="y" :value="y">{{ y }}</option>
        </select>
      </div>
      <p v-if="error" class="err small">{{ error }}</p>

      <template v-if="result">
        <div class="chips">
          <button class="chip" :class="{ on: L.area }" :disabled="!result.crops.length" @click="naip.toggle('area')"
                  title="Area covered by the true labels (hand-labelled image crops). Outside it nothing was labelled.">
            <span class="ic area"></span> Labelled area
          </button>
          <button class="chip" :class="{ on: L.rgb }" @click="naip.toggle('rgb')" title="NAIP aerial image, true colour">
            <span class="ic rgb"></span> RGB
          </button>
          <button class="chip" :class="{ on: L.ndvi }" @click="naip.toggle('ndvi')"
                  title="Vegetation index from red and near infrared: green = vegetation, brown = bare / built">
            <span class="ic ndvi"></span> NDVI
          </button>
          <button class="chip" :class="{ on: L.ventura }" :disabled="!result.model" @click="naip.toggle('ventura')"
                  :title="result.model ? 'Trees found in the image by the Ventura et al. model' : 'Ventura model weights not found'">
            <span class="ic ventura"></span> Ventura <b>{{ result.ventura.length }}</b>
          </button>
          <button class="chip" :class="{ on: L.truth }" :disabled="!truthNow.length" @click="naip.toggle('truth')"
                  title="Hand-placed tree positions (Ventura et al. data, CC BY 4.0), only inside the labelled area">
            <span class="ic truth"></span> True labels <b>{{ truthNow.length }}</b>
          </button>
        </div>
        <p class="dim small">
          NAIP {{ result.year }}<template v-if="labelYear"> · true labels {{ labelYear }}</template>
          <template v-else> · no true labels here</template>
          <template v-if="result.note"> · {{ result.note }}</template>
        </p>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useNaipStore } from '../../stores/naip.js'
import { getNaipTile, getNaipPatch } from '../../api/client.js'

// scope 'tile' = whole loaded file (2D view), 'patch' = the open patch (3D view)
const props = defineProps({ scope: { type: String, default: 'patch' } })

const route = useRoute()
const naip = useNaipStore()
const L = naip.layers
const loading = ref(false)
const error = ref('')
const year = ref(null)

const result = computed(() => (props.scope === 'tile' ? naip.tile : naip.patch))
const labelYear = computed(() => naip.labelYear(result.value))
const truthNow = computed(() => (result.value?.truth || []).filter(t => t.year === labelYear.value))

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const res = props.scope === 'tile'
      ? await getNaipTile(route.params.id, { year: year.value })
      : await getNaipPatch(route.params.id, route.params.patchId, { year: year.value })
    if (props.scope === 'tile') naip.tile = res.data
    else naip.patch = res.data
    year.value = res.data.year
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

// a different file in the 2D view: its layers no longer fit
watch(() => route.params.id, () => { if (props.scope === 'tile') { naip.tile = null; year.value = null } })

onMounted(() => { if (!naip.status.checked) naip.checkStatus() })
onBeforeUnmount(() => { if (props.scope === 'patch') naip.patch = null })
</script>

<style scoped>
.naip-panel { color: #eee; }
.panel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
h3 { margin: 0; font-size: 14px; }
.state { font-size: 11px; color: #667; border: 1px solid #334; border-radius: 8px; padding: 1px 7px; }
.state.on { color: #8d8; border-color: #3a5a3a; }
.small { font-size: 12px; }
.dim { color: #88a; }
.err { color: #f88; }
code { font-size: 11px; color: #ccf; }
.row { display: flex; align-items: center; gap: 6px; margin: 6px 0; }
.sel { background: #1a1a33; color: #eee; border: 1px solid #334; border-radius: 4px; font-size: 12px; padding: 4px; }
.run-btn {
  flex: 1; padding: 6px; border-radius: 4px; border: 1px solid #446;
  background: #24244a; color: #ccf; cursor: pointer; font-size: 12px;
}
.run-btn:hover:not(:disabled) { background: #30305e; }
.run-btn:disabled { opacity: 0.5; cursor: default; }
.chips { display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0 4px; }
.chip {
  display: inline-flex; align-items: center; gap: 5px; padding: 3px 8px; border-radius: 12px;
  border: 1px solid #334; background: #15152c; color: #778; font-size: 11.5px; cursor: pointer;
}
.chip.on { background: #26264c; color: #eef; border-color: #556; }
.chip:disabled { opacity: 0.35; cursor: default; }
.chip b { color: inherit; font-weight: 600; }
.ic { display: inline-block; width: 10px; height: 10px; flex-shrink: 0; }
.ic.area { border: 1.5px dashed #46e0ff; }
.ic.rgb { background: linear-gradient(135deg, #c44 0 33%, #4a4 33% 66%, #46c 66%); border-radius: 2px; }
.ic.ndvi { background: linear-gradient(90deg, #785032, #c8be78, #1e7828); border-radius: 2px; }
.ic.ventura { background: #ff46a2; border-radius: 50%; }
.ic.truth { border: 2px solid #46e0ff; border-radius: 50%; width: 8px; height: 8px; }
.chip:not(.on) .ic { opacity: 0.4; }
</style>
