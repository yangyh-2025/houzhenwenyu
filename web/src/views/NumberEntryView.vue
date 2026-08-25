<template>
  <div class="page">
    <!-- F2 entry mode -->
    <template v-if="mode === 'entry'">
      <h1 class="title">请输入您的就诊号</h1>

      <div
        class="digits-display card"
        aria-live="polite"
      >
        <span v-if="digits" class="digits">{{ digits }}</span>
        <span v-else class="digits digits-empty">请按下方大数字键</span>
      </div>

      <p v-if="hint" class="hint-bar warn" role="alert">{{ hint }}</p>

      <div class="stack">
        <button type="button" class="btn-big primary" @click="onConfirm">确认</button>
      </div>

      <NumberPad @press="onKey"></NumberPad>

      <p class="footnote">号码限 1-12 位数字。按错了可用「删除」逐位回退，或「清空」重输。</p>
    </template>

    <!-- F2 confirm step -->
    <template v-if="mode === 'confirm'">
      <h1 class="title">请核对您的就诊号</h1>

      <div class="confirm-card">
        <p class="confirm-label">您的就诊号是</p>
        <p class="confirm-number">{{ digits }}</p>
      </div>

      <div class="stack">
        <button
          type="button"
          class="btn-big primary"
          :disabled="busy"
          @click="onStartConsult"
        >
          没错，开始问诊
        </button>
        <button type="button" class="btn-big secondary" :disabled="busy" @click="onReenter">
          重新输入
        </button>
      </div>
    </template>

    <!-- mic permission overlay (W1: warmup retry must run in THIS button's click) -->
    <div v-if="permOverlay" class="overlay-mask" role="dialog" aria-modal="true" aria-label="录音权限提示">
      <div class="overlay-card">
        <h2>{{ permTitle }}</h2>
        <p>{{ permNote }}</p>
        <p class="alt">{{ permAlt }}</p>
        <div class="stack">
          <button type="button" class="btn-big primary" @click="retryMic">我已开启，重新尝试</button>
          <button type="button" class="btn-big secondary" @click="backToConsent">返回</button>
        </div>
      </div>
    </div>

    <!-- create-failure big text message -->
    <p v-if="createError" class="hint-bar error create-error" role="alert">
      {{ createError }}
    </p>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import NumberPad from '@/components/NumberPad.vue'
import { request, ApiError, binaryAudioRequest } from '@/api/api.js'
import { tts } from '@/lib/tts.js'
import { recorder } from '@/lib/recorder.js'
import { needsSafariGuide as detectedNeedsSafariGuide } from '@/lib/env.js'
import { setConsultation } from '@/store/session.js'

var router = useRouter()
var mode = ref('entry')
var digits = ref('')
var hint = ref('')
var busy = ref(false)
var permOverlay = ref(false)
// 评审 F-R3：iOS+微信环境开权限也录不了音 → 走 Safari 引导话术
var needsSafari = detectedNeedsSafariGuide
var permTitle = computed(function () {
  return needsSafari ? '苹果手机请用Safari打开' : '无法访问麦克风'
})
var permNote = computed(function () {
  return needsSafari
    ? '当前的微信网页里没法使用麦克风。请点右上角「…」，选择在Safari中打开网页，再进行语音问诊。'
    : '请在手机设置里允许微信（或浏览器）使用麦克风，开启后回来点下面的按钮继续。'
})
var permAlt = computed(function () {
  return needsSafari
    ? '如果无法打开Safari，也可以直接等候叫号就诊，您的正常看病不会受影响。'
    : '如果无法开启权限，将无法进行语音问诊，请正常等候叫号就诊。'
})
var createError = ref('')
var pendingCreate = null

var MAX_LEN = 12

function onKey(k) {
  hint.value = ''
  if (k === '删除') {
    digits.value = digits.value.slice(0, -1)
    return
  }
  if (k === '清空') {
    digits.value = ''
    return
  }
  if (digits.value.length >= MAX_LEN) {
    hint.value = '已达最长位数'
    return
  }
  digits.value += k
}

function onConfirm() {
  if (!digits.value) {
    hint.value = '请先输入您的就诊号'
    return
  }
  mode.value = 'confirm'
}

function onReenter() {
  mode.value = 'entry'
  digits.value = ''
  hint.value = ''
}

function backToConsent() {
  router.replace('/patient')
}

// W1/W5: everything gesture-sensitive starts inside this click handler.
function onStartConsult() {
  if (busy.value) return
  busy.value = true
  createError.value = ''
  var visitNumber = digits.value

  // 1. TTS element unlock - must stay synchronous in the gesture stack.
  tts.unlock()

  // 2. Fire the create request right away (async is fine, not gesture-bound).
  pendingCreate = binaryAudioRequest('/api/patient/consultations', {
    visit_number: visitNumber,
  })

  // 3. getUserMedia warmup - the CALL must be synchronous in the gesture.
  recorder.warmup().then(function () {
    return proceedToConsult(visitNumber)
  }, function (e) {
    busy.value = false
    permOverlay.value = true
  })
}

function proceedToConsult(visitNumber) {
  busy.value = true
  pendingCreate.then(function (resp) {
    // 二进制模式：meta+blob 组装为会话首轮（带宽优化直传）
    setConsultation({
      session_id: resp.meta.session_id,
      rounds_limit: resp.meta.rounds_limit,
      first_round: { text: resp.meta.text || '', audio_blob: (resp.blob && resp.blob.size > 100) ? resp.blob : null },
      resumed: !!resp.meta.resumed,
    }, visitNumber)
    router.push('/patient/consult')
  }).catch(function (e) {
    busy.value = false
    if (e instanceof ApiError) {
      createError.value = e.message
    } else {
      createError.value = '网络不稳定，请检查网络后重试'
    }
  })
}

// Permission overlay retry: warmup re-runs synchronously inside THIS click.
function retryMic() {
  permOverlay.value = false
  var visitNumber = digits.value
  recorder.warmup().then(function () {
    proceedToConsult(visitNumber)
  }, function () {
    permOverlay.value = true
  })
}
</script>

<style scoped>
.digits-display {
  min-height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: var(--sp-4) 0;
}

.digits {
  font-size: var(--fs-huge);
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.2;
}

.digits-empty {
  font-size: var(--fs-body);
  color: var(--c-muted);
  font-weight: 400;
}

.title {
  font-size: var(--fs-title);
  margin: var(--sp-4) 0;
}

.confirm-card {
  border: 3px solid var(--c-primary);
  border-radius: 20px;
  background: var(--c-primary-light);
  text-align: center;
  padding: var(--sp-5) var(--sp-4);
  margin: var(--sp-4) 0;
}

.confirm-label {
  font-size: var(--fs-big);
  margin: 0 0 var(--sp-3);
  color: var(--c-primary-dark);
}

.confirm-number {
  font-size: var(--fs-huge);
  font-weight: 700;
  letter-spacing: 0.08em;
  margin: 0;
  line-height: 1.15;
  color: var(--c-text);
  word-break: break-all;
}

.stack > button + button,
.stack > button + button { margin-top: 16px; }

.stack {
  margin: var(--sp-4) 0;
}

.keypad {
  margin-top: var(--sp-5);
}

.footnote {
  font-size: var(--fs-small);
  color: var(--c-muted);
  line-height: 1.5;
}

.alt {
  font-size: var(--fs-small);
}

.create-error {
  margin-top: var(--sp-4);
}
</style>
