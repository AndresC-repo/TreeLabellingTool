<template>
  <div class="dataset-page">
    <header class="top">
      <router-link to="/" class="back">← Labelling tool</router-link>
      <h1>Dataset overview</h1>
      <span
        class="folder"
        :class="{ off: data && !data.labels_folder.connected }"
        :title="data?.labels_folder.path"
      >
        {{ data ? (data.labels_folder.connected ? '● data/labels connected' : '● labels folder not connected') : '' }}
      </span>
      <div class="top-actions">
        <button @click="rescan" :disabled="scanning" title="Pick up files in data/labels that weren't saved by the tool, refresh tree counts">
          {{ scanning ? 'Scanning…' : '⟳ Rescan labels folder' }}
        </button>
        <a :href="datasetCsvUrl" class="btn" download>⬇ CSV</a>
      </div>
    </header>

    <div v-if="loadError" class="load-error">
      Couldn't load the dataset: {{ loadError }} <button @click="load">Retry</button>
    </div>

    <template v-if="data">
      <!-- Summary -->
      <section class="summary">
        <div class="card">
          <div class="big">{{ totals.trees.toLocaleString() }}</div>
          <div class="lbl">labelled trees</div>
        </div>
        <div class="card">
          <div class="big">{{ totals.files.toLocaleString() }}</div>
          <div class="lbl">patches in data/labels</div>
        </div>
        <div class="card">
          <div class="big">{{ totals.zero }}</div>
          <div class="lbl">patches with 0 trees</div>
        </div>
        <div class="card">
          <div class="big">{{ data.sources.length }}</div>
          <div class="lbl">source tiles</div>
        </div>

        <div class="card wide">
          <div class="card-title">Trees by region</div>
          <div v-for="r in byRegion" :key="r.region" class="bar-row" @click="filters.region = filters.region === r.region ? '' : r.region">
            <span class="bar-lbl" :class="{ sel: filters.region === r.region }">{{ r.region || 'unknown' }}</span>
            <span class="bar-track"><span class="bar" :style="{ width: (100 * r.trees / maxRegionTrees) + '%' }"></span></span>
            <span class="bar-val">{{ r.trees }} trees · {{ r.files }} patches</span>
          </div>
          <p v-if="!byRegion.length" class="empty">Nothing yet — rescan the labels folder or save a patch.</p>
        </div>

        <div class="card wide">
          <div class="card-title">Patches by status</div>
          <div class="chips">
            <button
              v-for="s in data.patch_statuses" :key="s"
              class="chip" :class="['st-' + slug(s), { sel: filters.status === s }]"
              @click="filters.status = filters.status === s ? '' : s"
            >{{ s }} <b>{{ statusCount[s] || 0 }}</b></button>
          </div>
        </div>
      </section>

      <!-- Tabs + filters -->
      <nav class="tabs">
        <button :class="{ on: tab === 'patches' }" @click="tab = 'patches'">Patches <span>{{ filteredPatches.length }}</span></button>
        <button :class="{ on: tab === 'tiles' }" @click="tab = 'tiles'">Source tiles <span>{{ filteredSources.length }}</span></button>
        <div class="filters">
          <input v-model="filters.q" placeholder="Search name or notes…" />
          <select v-model="filters.region">
            <option value="">All regions</option>
            <option v-for="r in regions" :key="r" :value="r">{{ r || 'unknown' }}</option>
          </select>
          <select v-if="tab === 'patches'" v-model="filters.status">
            <option value="">All statuses</option>
            <option v-for="s in data.patch_statuses" :key="s" :value="s">{{ s }}</option>
          </select>
          <select v-else v-model="filters.tileStatus">
            <option value="">All statuses</option>
            <option v-for="s in data.source_statuses" :key="s" :value="s">{{ s }}</option>
          </select>
          <button v-if="anyFilter" class="clear" @click="clearFilters">Clear</button>
        </div>
      </nav>

      <!-- Patches table -->
      <div v-if="tab === 'patches'" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th @click="sortBy('file')">File</th>
              <th @click="sortBy('region')">Region</th>
              <th @click="sortBy('trees')" class="num">Trees</th>
              <th @click="sortBy('points')" class="num">Points</th>
              <th @click="sortBy('status')">Status</th>
              <th>Notes</th>
              <th @click="sortBy('exported_at')">Saved</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in sortedPatches" :key="p.key" :class="{ excluded: p.status === 'excluded' }">
              <td class="file">
                <div class="fname" :title="p.file || '(not saved yet)'">
                  {{ p.file || '— not saved yet' }}
                  <span v-if="p.file_missing" class="badge miss" title="The file is no longer in data/labels">missing</span>
                  <span v-if="p.origin === 'folder'" class="badge" title="Found in data/labels, not saved by this tool version">folder</span>
                </div>
                <div v-if="p.source" class="sub">{{ p.source }} · patch {{ p.patch_number }}</div>
              </td>
              <td>{{ regionOf(p) || '—' }}</td>
              <td class="num" :class="{ zero: p.trees === 0 }">{{ p.trees >= 0 ? p.trees : '?' }}</td>
              <td class="num">{{ p.points ? p.points.toLocaleString() : '' }}</td>
              <td>
                <select :value="p.status" class="status" :class="'st-' + slug(p.status)" @change="setPatch(p, { status: $event.target.value })">
                  <option v-for="s in data.patch_statuses" :key="s" :value="s">{{ s }}</option>
                </select>
              </td>
              <td>
                <input class="notes" :value="p.notes" placeholder="add a note"
                       @change="setPatch(p, { notes: $event.target.value })" @keydown.enter="$event.target.blur()" />
              </td>
              <td class="date">{{ fmtDate(p.exported_at) }}</td>
              <td>
                <router-link v-if="p.openable" :to="`/session/${p.session_id}/patch/${p.patch_id}?n=${p.patch_number}`" class="open" title="Open this patch in the 3D view">Open</router-link>
              </td>
            </tr>
            <tr v-if="!sortedPatches.length"><td colspan="8" class="empty">No patches match.</td></tr>
          </tbody>
        </table>
      </div>

      <!-- Source tiles table -->
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Source tile</th>
              <th>State</th>
              <th>City</th>
              <th>Units</th>
              <th class="num">Patches</th>
              <th class="num">Saved</th>
              <th class="num">Trees</th>
              <th>Status</th>
              <th>Notes</th>
              <th>Last opened</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filteredSources" :key="s.name">
              <td class="file"><div class="fname" :title="s.name">{{ s.name }}</div></td>
              <td><input class="short" :value="s.state" maxlength="4" @change="setSource(s, { state: $event.target.value.trim().toUpperCase() })" /></td>
              <td><input class="mid" :value="s.city" placeholder="city" @change="setSource(s, { city: $event.target.value.trim() })" /></td>
              <td :class="{ warn: s.units_source === 'uncertain' }" :title="s.units_source">{{ s.units || '' }}</td>
              <td class="num">{{ s.patches }}</td>
              <td class="num">{{ s.exported }}</td>
              <td class="num">{{ s.trees }}</td>
              <td>
                <select :value="s.status" class="status" :class="'st-' + slug(s.status)" @change="setSource(s, { status: $event.target.value })">
                  <option v-for="st in data.source_statuses" :key="st" :value="st">{{ st }}</option>
                </select>
              </td>
              <td><input class="notes" :value="s.notes" placeholder="add a note" @change="setSource(s, { notes: $event.target.value })" @keydown.enter="$event.target.blur()" /></td>
              <td class="date">{{ fmtDate(s.last_opened) }}</td>
            </tr>
            <tr v-if="!filteredSources.length"><td colspan="10" class="empty">No tiles yet — tiles appear here when you load them in the tool.</td></tr>
          </tbody>
        </table>
      </div>
      <p class="foot">
        Saved in <code>{{ data.labels_folder.registry }}</code> next to the labels folder.
        <span v-if="data.last_scan">Last folder scan {{ fmtDate(data.last_scan) }}.</span>
      </p>
    </template>
    <div v-else-if="!loadError" class="loading">Loading…</div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { getDataset, scanLabelsFolder, updateDatasetSource, updateDatasetPatch, datasetCsvUrl } from '../api/client.js'
import { useToastStore } from '../stores/toast.js'

const toast = useToastStore()
const data = ref(null)
const loadError = ref(null)
const scanning = ref(false)
const tab = ref('patches')
const filters = reactive({ q: '', region: '', status: '', tileStatus: '' })
const sort = reactive({ key: 'file', dir: 1 })

async function load() {
  loadError.value = null
  try {
    data.value = (await getDataset()).data
  } catch (err) {
    loadError.value = err.response?.data?.detail || err.message
  }
}

async function rescan() {
  scanning.value = true
  try {
    const r = (await scanLabelsFolder()).data
    toast.success(`Scanned ${r.files} files: ${r.added} new, ${r.updated} updated.`)
    await load()
  } catch (err) {
    toast.error('Scan failed: ' + (err.response?.data?.detail || err.message))
  } finally {
    scanning.value = false
  }
}

onMounted(async () => {
  await load()
  // First visit: nothing scanned yet → scan the folder once automatically
  if (data.value && !data.value.last_scan) rescan()
})

// ── edits (optimistic, saved immediately) ──
async function setPatch(p, fields) {
  const before = { ...p }
  Object.assign(p, fields)
  try {
    await updateDatasetPatch(p.key, fields)
  } catch (err) {
    Object.assign(p, before)
    toast.error('Not saved: ' + (err.response?.data?.detail || err.message))
  }
}
async function setSource(s, fields) {
  const before = { ...s }
  Object.assign(s, fields)
  try {
    await updateDatasetSource(s.name, fields)
    if ('city' in fields || 'state' in fields) await load()   // regions of its patches change
  } catch (err) {
    Object.assign(s, before)
    toast.error('Not saved: ' + (err.response?.data?.detail || err.message))
  }
}

// ── derived ──
const slug = s => (s || '').replace(/\s+/g, '-')
const regionOf = p => [p.state, p.city].filter(Boolean).join(' · ')   // shown in the table
const regionKey = p => p.state || p.city || ''                           // grouping & filter (state first)
const counted = p => p.file && !p.file_missing && p.status !== 'excluded'

const totals = computed(() => {
  const ps = (data.value?.patches ?? []).filter(counted)
  return {
    trees: ps.reduce((n, p) => n + Math.max(0, p.trees ?? 0), 0),
    files: ps.length,
    zero: ps.filter(p => p.trees === 0).length,
  }
})

const byRegion = computed(() => {
  const m = new Map()
  for (const p of (data.value?.patches ?? []).filter(counted)) {
    const r = regionKey(p)
    const e = m.get(r) ?? { region: r, trees: 0, files: 0 }
    e.trees += Math.max(0, p.trees ?? 0); e.files++
    m.set(r, e)
  }
  return [...m.values()].sort((a, b) => b.trees - a.trees)
})
const maxRegionTrees = computed(() => Math.max(1, ...byRegion.value.map(r => r.trees)))

const statusCount = computed(() => {
  const c = {}
  for (const p of data.value?.patches ?? []) c[p.status] = (c[p.status] ?? 0) + 1
  return c
})

const regions = computed(() => {
  const set = new Set((data.value?.patches ?? []).map(regionKey))
  for (const s of data.value?.sources ?? []) set.add(regionKey(s))
  return [...set].sort()
})

const matchQ = (...xs) => !filters.q || xs.some(x => (x || '').toLowerCase().includes(filters.q.toLowerCase()))

const filteredPatches = computed(() => (data.value?.patches ?? []).filter(p =>
  (!filters.region || regionKey(p) === filters.region) &&
  (!filters.status || p.status === filters.status) &&
  matchQ(p.file, p.source, p.notes)))

const sortedPatches = computed(() => {
  const key = sort.key, dir = sort.dir
  const val = p => key === 'region' ? regionOf(p) : (p[key] ?? (typeof p.trees === 'number' && key !== 'file' ? -1 : ''))
  return [...filteredPatches.value].sort((a, b) => {
    const x = val(a), y = val(b)
    return (x > y ? 1 : x < y ? -1 : 0) * dir
  })
})

const filteredSources = computed(() => (data.value?.sources ?? []).filter(s =>
  (!filters.region || regionKey(s) === filters.region) &&
  (!filters.tileStatus || s.status === filters.tileStatus) &&
  matchQ(s.name, s.notes, s.city)))

const anyFilter = computed(() => filters.q || filters.region || filters.status || filters.tileStatus)
function clearFilters() { Object.assign(filters, { q: '', region: '', status: '', tileStatus: '' }) }
function sortBy(key) {
  if (sort.key === key) sort.dir *= -1
  else { sort.key = key; sort.dir = key === 'trees' || key === 'points' || key === 'exported_at' ? -1 : 1 }
}
function fmtDate(t) {
  if (!t) return ''
  const d = new Date(t * 1000)
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short' }) + ' ' +
         d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.dataset-page { min-height: 100vh; padding: 18px 24px 40px; color: #cce; }
.top { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
.back { color: #7af; text-decoration: none; font-size: 13px; }
.back:hover { text-decoration: underline; }
h1 { font-size: 1.4rem; color: #adf; font-weight: 600; }
.folder { font-size: 12px; color: #7c9; }
.folder.off { color: #fb4; }
.top-actions { margin-left: auto; display: flex; gap: 8px; }
button, .btn {
  background: #2a2a4e; color: #cce; border: 1px solid #445; padding: 6px 12px;
  border-radius: 6px; cursor: pointer; font-size: 13px; text-decoration: none; white-space: nowrap;
}
button:hover:not(:disabled), .btn:hover { background: #3a3a6e; }
button:disabled { opacity: 0.6; cursor: default; }

.load-error { color: #fcc; margin-bottom: 12px; }
.loading { color: #889; }

/* Summary */
.summary { display: grid; grid-template-columns: repeat(4, minmax(130px, 1fr)) repeat(2, minmax(260px, 2fr)); gap: 12px; margin-bottom: 18px; }
@media (max-width: 1300px) { .summary { grid-template-columns: repeat(4, 1fr); } .card.wide { grid-column: span 2; } }
.card { background: #0d0d1f; border: 1px solid #2a2a44; border-radius: 10px; padding: 12px 14px; }
.big { font-size: 1.7rem; font-weight: 600; color: #e6ecff; font-variant-numeric: tabular-nums; }
.lbl { font-size: 12px; color: #889; }
.card-title { font-size: 11px; color: #889; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
.bar-row { display: grid; grid-template-columns: 110px 1fr auto; gap: 8px; align-items: center; font-size: 12px; padding: 2px 0; cursor: pointer; }
.bar-lbl { color: #aab; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-lbl.sel { color: #adf; font-weight: 600; }
.bar-track { height: 8px; background: #1a1a33; border-radius: 4px; overflow: hidden; }
.bar { display: block; height: 100%; background: #5a8ad8; border-radius: 4px; }
.bar-val { color: #889; font-variant-numeric: tabular-nums; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-size: 12px; padding: 4px 10px; border-radius: 12px; }
.chip b { margin-left: 4px; color: #fff; }
.chip.sel { outline: 2px solid #7ab3ff; }

/* status colours (chips + selects) */
.st-in-progress { border-color: #6a6a3a; }
.st-labelled    { border-color: #3a6a8a; }
.st-needs-fix   { border-color: #8a4a3a; color: #fb9; }
.st-reviewed    { border-color: #3a7a4a; color: #9d9; }
.st-excluded    { border-color: #444; color: #778; }
.st-to-do       { border-color: #555; }
.st-done        { border-color: #3a7a4a; color: #9d9; }
.st-skipped     { border-color: #444; color: #778; }

/* Tabs + filters */
.tabs { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.tabs > button { background: none; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 6px 10px; color: #889; }
.tabs > button.on { color: #adf; border-bottom-color: #7ab3ff; }
.tabs > button span { font-size: 11px; color: #667; margin-left: 4px; }
.filters { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; }
.filters input, .filters select, select.status, input.notes, input.short, input.mid {
  background: #1a1a33; color: #cce; border: 1px solid #334; border-radius: 5px; padding: 5px 8px; font-size: 12px;
}
.filters input { width: 210px; }
.clear { font-size: 12px; padding: 4px 10px; }

/* Tables */
.table-wrap { overflow-x: auto; border: 1px solid #2a2a44; border-radius: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
thead th {
  position: sticky; top: 0; background: #14142a; color: #889; font-weight: 600; text-align: left;
  padding: 8px 10px; border-bottom: 1px solid #2a2a44; cursor: pointer; user-select: none; white-space: nowrap;
}
td { padding: 6px 10px; border-bottom: 1px solid #20203a; vertical-align: middle; }
tbody tr:hover { background: #171733; }
tr.excluded td { opacity: 0.5; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
td.zero { color: #fb4; }
td.warn { color: #fb4; }
.file { max-width: 520px; }
.fname { font-family: monospace; font-size: 12px; color: #dde; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sub { font-size: 11px; color: #667; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { font-family: system-ui, sans-serif; font-size: 10px; padding: 0 5px; border-radius: 3px; background: #2a2a4e; color: #99b; margin-left: 4px; }
.badge.miss { background: #4a2a2a; color: #fbb; }
input.notes { width: 100%; min-width: 160px; }
input.short { width: 50px; }
input.mid { width: 120px; }
.date { color: #889; white-space: nowrap; font-size: 12px; }
.open { color: #7af; font-size: 12px; text-decoration: none; }
.open:hover { text-decoration: underline; }
.empty { color: #778; font-size: 12px; text-align: center; padding: 18px; }
.foot { margin-top: 10px; font-size: 11px; color: #667; }
.foot code { color: #88a; }
</style>
