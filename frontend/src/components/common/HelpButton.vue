<template>
  <div class="help-anchor">
    <button
      class="help-btn"
      :class="{ pulse: showTip }"
      @click.stop="toggle"
      :title="`Guide for this page  [?]`"
      aria-label="Help"
    >?</button>

    <!-- One-time hint, shown on the first visit of each page -->
    <transition name="fade">
      <div v-if="showTip" class="tip" @click.stop>
        <span>New here? A quick guide to this page.</span>
        <button class="tip-open" @click="openGuide">Show me</button>
        <button class="tip-close" @click="dismissTip" title="Don't show again">✕</button>
      </div>
    </transition>
  </div>

  <teleport to="body">
    <transition name="slide">
      <aside v-if="open" class="help-drawer" role="dialog" aria-label="Guide" @click.stop>
        <header>
          <h2>{{ guide.title }}</h2>
          <button class="close" @click="open = false" title="Close [Esc]">✕</button>
        </header>
        <div class="body">
          <p class="intro">{{ guide.intro }}</p>
          <section v-for="s in guide.sections" :key="s.heading">
            <h3>{{ s.heading }}</h3>
            <ol v-if="s.steps"><li v-for="(t, i) in s.steps" :key="i" v-html="t" /></ol>
            <ul v-if="s.bullets"><li v-for="(t, i) in s.bullets" :key="i" v-html="t" /></ul>
            <table v-if="s.keys" class="keys">
              <tr v-for="[k, what] in s.keys" :key="k">
                <td><kbd v-for="part in k.split(' / ')" :key="part">{{ part }}</kbd></td>
                <td>{{ what }}</td>
              </tr>
            </table>
          </section>
        </div>
        <footer>
          <span>Press <kbd>?</kbd> to open or close this guide.</span>
          <button class="reset" @click="resetTips" title="Show the 'New here?' hint again on every page">Show first-time hints again</button>
        </footer>
      </aside>
    </transition>
  </teleport>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { HELP } from './helpContent.js'

const props = defineProps({ page: { type: String, required: true } })
const guide = computed(() => HELP[props.page] ?? HELP.upload)

const open = ref(false)
const showTip = ref(false)

// Pages whose hint was already seen, remembered in this browser. If storage is
// blocked the hint simply shows once per visit.
const KEY = 'labellingTool.helpSeen'
const memory = new Set()
function seenPages() {
  try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')) } catch { return memory }
}
function markSeen() {
  const s = seenPages(); s.add(props.page); memory.add(props.page)
  try { localStorage.setItem(KEY, JSON.stringify([...s])) } catch { /* ignore */ }
}

function openGuide() { open.value = true; showTip.value = false; markSeen() }
function dismissTip() { showTip.value = false; markSeen() }
function toggle() { open.value ? (open.value = false) : openGuide() }
function resetTips() {
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
  memory.clear()
  open.value = false
  showTip.value = true
}

function onKey(e) {
  if (e.target.closest?.('input, textarea, select, [contenteditable]')) return
  if (e.key === '?') { e.preventDefault(); toggle() }
  else if (e.key === 'Escape' && open.value) { e.stopImmediatePropagation(); open.value = false }
}
function onOutside() { if (open.value) open.value = false }

let timer
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  window.addEventListener('click', onOutside)
  if (!seenPages().has(props.page)) timer = setTimeout(() => { showTip.value = true }, 900)
})
onBeforeUnmount(() => {
  clearTimeout(timer)
  window.removeEventListener('keydown', onKey, true)
  window.removeEventListener('click', onOutside)
})
</script>

<style scoped>
.help-anchor { position: relative; display: inline-flex; flex-shrink: 0; }
.help-btn {
  width: 26px; height: 26px; border-radius: 50%; padding: 0;
  background: #1c2440; color: #9bd; border: 1px solid #3a4a6e;
  font: 600 14px/1 system-ui, sans-serif; cursor: pointer;
}
.help-btn:hover { background: #26325a; color: #cdf; border-color: #5a7ab0; }
.help-btn.pulse { animation: pulse 1.6s ease-out 3; }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(120, 170, 255, 0.55); }
  100% { box-shadow: 0 0 0 10px rgba(120, 170, 255, 0); }
}

.tip {
  position: absolute; top: calc(100% + 10px); right: -4px; z-index: 60;
  display: flex; align-items: center; gap: 8px; white-space: nowrap;
  background: #22305a; color: #dde6ff; border: 1px solid #4a64a0; border-radius: 8px;
  padding: 7px 8px 7px 12px; font-size: 12.5px; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4);
}
.tip::before {
  content: ''; position: absolute; top: -6px; right: 11px; width: 10px; height: 10px;
  background: #22305a; border-left: 1px solid #4a64a0; border-top: 1px solid #4a64a0; transform: rotate(45deg);
}
.tip-open { background: #3a5a9e; color: #fff; border: none; border-radius: 5px; padding: 3px 9px; font-size: 12px; cursor: pointer; }
.tip-open:hover { background: #4a6abe; }
.tip-close { background: none; border: none; color: #9ab; cursor: pointer; font-size: 12px; padding: 2px 4px; }
.tip-close:hover { color: #fff; }

.help-drawer {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 1000;
  width: min(390px, 100vw); display: flex; flex-direction: column;
  background: #10142a; color: #d5dcf0; border-left: 1px solid #334;
  box-shadow: -10px 0 30px rgba(0, 0, 0, 0.45); font-size: 13.5px; line-height: 1.5;
}
.help-drawer header { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px 10px; border-bottom: 1px solid #262c48; }
.help-drawer h2 { font-size: 16px; color: #adf; font-weight: 600; }
.close { background: none; border: none; color: #89a; font-size: 15px; cursor: pointer; padding: 4px 6px; }
.close:hover { color: #fff; }
.body { flex: 1; overflow-y: auto; padding: 12px 18px 18px; }
.intro { color: #aab4d0; margin-bottom: 12px; }
section { margin-top: 14px; }
h3 { font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.06em; color: #7f8fb8; margin-bottom: 6px; }
ol, ul { padding-left: 20px; display: flex; flex-direction: column; gap: 6px; }
li :deep(b) { color: #eef2ff; font-weight: 600; }
li :deep(code) { font-size: 12px; background: #1c2240; padding: 0 4px; border-radius: 3px; color: #cfe; }
.keys { width: 100%; border-collapse: collapse; }
.keys td { padding: 4px 0; vertical-align: top; border-bottom: 1px solid #1d2240; }
.keys td:first-child { width: 46%; white-space: nowrap; }
kbd {
  display: inline-block; margin-right: 4px; padding: 1px 6px; font: 11.5px ui-monospace, monospace;
  background: #1e2546; border: 1px solid #3a4470; border-bottom-width: 2px; border-radius: 4px; color: #dfe6ff;
}
footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 18px; border-top: 1px solid #262c48; font-size: 11.5px; color: #7a86a8; }
.reset { background: none; border: none; color: #7a9ad8; font-size: 11.5px; cursor: pointer; text-decoration: underline; padding: 0; }
.reset:hover { color: #adf; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.25s, transform 0.25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-4px); }
.slide-enter-active, .slide-leave-active { transition: transform 0.22s ease, opacity 0.22s; }
.slide-enter-from, .slide-leave-to { transform: translateX(30px); opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .help-btn.pulse { animation: none; }
  .fade-enter-active, .fade-leave-active, .slide-enter-active, .slide-leave-active { transition: none; }
}
</style>
