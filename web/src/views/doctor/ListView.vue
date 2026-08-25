<template>
  <div class="page-doctor list-page">
    <div class="doc-header-bar">
      <h1>问诊记录</h1>
      <button type="button" class="btn-mid plain" @click="onLogout">退出登录</button>
    </div>

    <!-- Filters (F11, 2026-08-24): 仅保留就诊号查询（去除日期筛选） -->
    <div class="filters card">
      <label>就诊号
        <input
          v-model="q"
          type="text"
          inputmode="numeric"
          placeholder="输入号码可快速查找"
          @input="q = q.replace(/[^0-9]/g, '')"
        />
      </label>
      <button type="button" class="btn-mid primary" @click="onFilter">查询</button>
    </div>

    <p v-if="filterHint" class="hint-bar warn" role="alert">{{ filterHint }}</p>

    <!-- Record cards (F7): visit number big, time, rounds badge, summary preview -->
    <div class="records">
      <button
        v-for="it in items"
        :key="it.id"
        type="button"
        class="record-card"
        @click="openDetail(it.id)"
      >
        <div class="record-top">
          <span class="record-number">{{ it.visit_number }}</span>
          <span class="badge">{{ it.rounds }} 轮</span>
        </div>
        <p class="record-time">{{ fmtTime(it.submitted_at) }}</p>
        <p class="record-preview">AI摘要预览：{{ previewText(it) }}</p>
      </button>

      <p v-if="!items.length && !busy" class="empty">
        {{ emptyText }}
      </p>
    </div>

    <div class="list-actions stack">
      <button
        v-if="canLoadMore"
        type="button"
        class="btn-mid primary"
        :disabled="busy"
        @click="onLoadMore"
      >
        加载更多
      </button>
      <button type="button" class="btn-mid plain" :disabled="busy" @click="onRefresh">刷新</button>
    </div>

    <p v-if="loadError" class="hint-bar error" role="alert">
      {{ loadError }}
      <button type="button" class="btn-mid primary" @click="onRefresh">重试</button>
    </p>
  </div>
</template>

<script setup>
function previewText(it) {
  var t = it.summary_preview || ''
  var last = t.lastIndexOf('】')
  if (last > 0) t = t.slice(0, last + 1)
  return t || '未提及'
}
import { ref, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { request } from '@/api/api.js'

defineOptions({ name: 'DoctorListView' })

var router = useRouter()

var items = ref([])
var total = ref(0)
var page = ref(1)
var PAGE_SIZE = 20
var q = ref('')
var busy = ref(false)
var loadError = ref('')
var filterHint = ref('')
var firstLoaded = ref(false)

var canLoadMore = computed(function () {
  return items.value.length < total.value
})

var emptyText = computed(function () {
  return q.value ? '未找到符合条件的记录' : '暂无问诊记录'
})

function buildQuery() {
  var parts = []
  if (q.value) parts.push('q=' + encodeURIComponent(q.value))
  return parts.length ? '&' + parts.join('&') : ''
}

function fetchPage(pageNo, replace) {
  busy.value = true
  loadError.value = ''
  request('/api/doctor/consultations?page=' + pageNo + '&page_size=' + PAGE_SIZE + buildQuery())
    .then(function (data) {
      total.value = data.total
      page.value = data.page
      if (replace) {
        items.value = data.items
      } else {
        items.value = items.value.concat(data.items)
      }
      firstLoaded.value = true
    })
    .catch(function (e) {
      // F7: on failure keep already-shown records, just surface a retry hint.
      loadError.value = e.message || '加载失败，请重试'
    })
    .finally(function () {
      busy.value = false
    })
}

function onRefresh() {
  fetchPage(1, true)
}

function onLoadMore() {
  fetchPage(page.value + 1, false)
}

function onFilter() {
  filterHint.value = ''
  fetchPage(1, true)
}

function openDetail(id) {
  router.push('/doctor/records/' + id)
}

function onLogout() {
  request('/api/doctor/logout', { method: 'POST' })
    .catch(function () {})
    .then(function () {
      router.replace('/doctor/login')
    })
}

onMounted(function () {
  if (!firstLoaded.value) onRefresh()
})

// Returning from detail (keep-alive): silently refresh to catch new records.
onActivated(function () {
  if (firstLoaded.value) onRefresh()
})

function fmtTime(epochSeconds) {
  if (!epochSeconds) return ''
  var d = new Date(epochSeconds * 1000)
  return d.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-3);
  align-items: end;
  margin-bottom: var(--sp-4);
}

.filters label {
  font-size: var(--fs-small);
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-weight: 700;
}

.filters input {
  min-height: 48px;
  border: 2px solid var(--c-border);
  border-radius: 10px;
  padding: 8px 10px;
  font-size: var(--fs-body);
}

.record-card {
  width: 100%;
  text-align: left;
  background: #fff;
  border: 2px solid var(--c-border);
  border-radius: 14px;
  padding: var(--sp-4);
  margin-bottom: var(--sp-4);
  cursor: pointer;
}

.record-card:active {
  background: #f4f6f5;
}

.record-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.record-number {
  font-size: var(--fs-big);
  font-weight: 700;
}

.badge {
  background: var(--c-primary-light);
  color: var(--c-primary-dark);
  font-size: var(--fs-small);
  font-weight: 700;
  padding: 4px 12px;
  border-radius: 999px;
}

.record-time {
  margin: 6px 0;
  font-size: var(--fs-small);
  color: var(--c-muted);
}

.record-preview {
  margin: 0;
  font-size: var(--fs-body);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.empty {
  text-align: center;
  font-size: var(--fs-body);
  color: var(--c-muted);
  padding: var(--sp-6) 0;
}

.list-actions {
  display: flex;
  gap: var(--sp-4);
  margin-top: var(--sp-4);
}

.list-actions button {
  flex: 1;
}
</style>

