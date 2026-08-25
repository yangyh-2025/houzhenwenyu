<template>
  <div class="page-doctor">
    <!-- F8: disclaimer fixed at top -->
    <div class="disclaimer" role="note">
      {{ detail.disclaimer || DEFAULT_DISCLAIMER }}
    </div>

    <button type="button" class="btn-mid plain back-btn" @click="goBack">返回列表</button>

    <div class="card head-card">
      <p class="head-number">{{ detail.visit_number }}</p>
      <p class="head-meta">
        提交时间：{{ fmtTime(detail.submitted_at) }} · 共 {{ detail.rounds }} 轮
      </p>
    </div>

    <!-- 辨证参考置顶（2026-08-25：患者序号下方、主诉之前，医生一眼先看）-->
    <div v-if="tcmField" class="field-block card field-tcm">
      <p class="field-label">{{ tcmField.label }}（AI 生成 · 仅供医生参考）</p>
      <p class="field-content">{{ tcmField.content }}</p>
    </div>

    <!-- 八栏目摘要 -->
    <div v-if="fields.length" class="fields">
      <div v-for="f in fields" :key="f.label" class="field-block card">
        <p class="field-label">{{ f.label }}</p>
        <p class="field-content">{{ f.content }}</p>
      </div>
    </div>
    <pre v-else-if="detail.summary_text" class="raw-summary card">{{ detail.summary_text }}</pre>
    <p v-else class="empty">暂无摘要内容</p>

    <p v-if="loadError" class="hint-bar error" role="alert">{{ loadError }}</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { request } from '@/api/api.js'

var router = useRouter()
var route = useRoute()
var DEFAULT_DISCLAIMER = '本摘要由AI整理，仅供面诊参考，请以面诊核实为准。'

var detail = ref({})
var loadError = ref('')

function _parseBlocks(text) {
  var re = /【([^】]+)】([^【]*)/g
  var out = []
  var seen = {}
  var m = re.exec(text)
  while (m !== null) {
    var label = m[1].trim()
    if (!seen[label]) {
      seen[label] = true
      out.push({
        label: label,
        content: (m[2] || '').trim() || '未提及',
      })
    }
    m = re.exec(text)
  }
  return out
}

// 辨证参考单独提取（置顶展示）
var tcmField = computed(function () {
  var blocks = _parseBlocks(detail.value.summary_text || '')
  for (var i = 0; i < blocks.length; i++) {
    if (blocks[i].label.indexOf('辨证') >= 0) return blocks[i]
  }
  return null
})

var fields = computed(function () {
  return _parseBlocks(detail.value.summary_text || '').filter(function (f) {
    return f.label.indexOf('辨证') < 0
  })
})

onMounted(function () {
  request('/api/doctor/consultations/' + route.params.id)
    .then(function (data) {
      detail.value = data || {}
    })
    .catch(function (e) {
      loadError.value = e.message || '加载失败，请重试'
    })
})

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.replace('/doctor')
  }
}

function fmtTime(epochSeconds) {
  if (!epochSeconds) return ''
  return new Date(epochSeconds * 1000).toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.disclaimer {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--c-warn-bg);
  color: var(--c-warn);
  font-size: var(--fs-small);
  font-weight: 700;
  padding: 10px 14px;
  border-radius: 10px;
  margin-bottom: var(--sp-4);
}

.back-btn {
  margin-bottom: var(--sp-4);
}

.head-card {
  text-align: center;
  margin-bottom: var(--sp-4);
}

.head-number {
  font-size: var(--fs-huge);
  font-weight: 700;
  letter-spacing: 0.06em;
  margin: 0 0 var(--sp-2);
}

.head-meta {
  margin: 0;
  font-size: var(--fs-body);
  color: var(--c-muted);
}

.fields .field-block {
  margin-bottom: var(--sp-3);
}

.field-tcm {
  border-left: 6px solid #c77d1e;
  background: #fff8ec;
}

.field-tcm .field-label {
  color: #9a5f10;
}

.field-label {
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--c-primary-dark);
  margin: 0 0 6px;
}

.field-content {
  font-size: var(--fs-body);
  line-height: 1.5;
  margin: 0;
}

.raw-summary {
  white-space: pre-wrap;
  font-family: inherit;
  font-size: var(--fs-body);
  line-height: 1.5;
}

.empty {
  text-align: center;
  font-size: var(--fs-body);
  color: var(--c-muted);
  padding: var(--sp-6) 0;
}
</style>
