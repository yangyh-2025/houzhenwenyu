<template>
  <div class="page consult">
    <StatusBanner
      v-if="state !== 'error'"
      :tone="bannerTone"
      :text="bannerText"
      :sub-text="uploadHint"
    />

    <!-- 采集进度条（2026-08-24）：当前阶段 + 剩余预期 -->
    <div v-if="stageNow > 0" class="progress card" role="status">
      <div class="progress-row">
        <span class="progress-label">问诊进度</span>
        <span class="progress-num">第 {{ stageNow }}/8 步</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: pctWidth }"></div>
      </div>
      <p class="progress-note">大约还剩 {{ remainCount }} 个小问题，问完就好，请放心</p>
    </div>

    <!-- 说话气泡：按住时显示波形与计时 -->
    <div v-if="holdActive" class="talk-bubble" role="status">
      <div class="talk-bars">
        <span class="bar b1"></span><span class="bar b2"></span><span class="bar b3"></span>
        <span class="bar b4"></span><span class="bar b5"></span>
      </div>
      <span class="talk-time">正在说话 {{ holdSec }}s</span>
    </div>

    <!-- 当前问题文字（语音+文字双通道）-->
    <div v-if="questionText && stateIsOneOf(['playing', 'listening', 'intro-ack'])" class="card q-card">
      <p class="q-label">当前问题</p>
      <p class="q-text">{{ questionText }}</p>
    </div>

    <!-- 介绍播毕：明白了 -->
    <div v-if="state === 'intro-ack'" class="controls stack">
      <button type="button" class="btn-big primary" @click="onIntroAck">明白了</button>
      <button type="button" class="btn-mid plain" @click="replayIntro">再听一遍</button>
    </div>

    <!-- 说话区：播报中可按住打断，聆听中按住说话 -->
    <div v-if="stateIsOneOf(['playing', 'listening'])" class="controls stack">
      <button
        type="button"
        class="btn-big primary hold-btn"
        :class="{ holding: holdActive }"
        @touchstart.prevent="holdStart"
        @touchend.prevent="holdEnd"
        @touchcancel="holdEnd"
        @mousedown.prevent="holdStart"
        @mouseup.prevent="holdEnd"
        @mouseleave="holdActive && holdEnd()"
      >{{ holdActive ? '松开 结束回答' : '按住 说话（可打断播报）' }}</button>
      <p v-if="holdHint" class="hint-bar warn" role="alert">{{ holdHint }}</p>
      <button v-if="state === 'listening'" type="button" class="btn-mid plain" @click="replayQuestion">再听一遍</button>
    </div>

    <!-- 3次静默：继续/结束 -->
    <div v-if="state === 'ask-continue'" class="overlay-mask" role="dialog" aria-modal="true" aria-label="继续或结束">
      <div class="overlay-card">
        <h2>您还在吗？</h2>
        <p>好一会儿没有听到您说话啦。想继续问诊，还是先到这里？</p>
        <div class="stack">
          <button type="button" class="btn-big primary" @click="onAskContinue(true)">继续问答</button>
          <button type="button" class="btn-big secondary" @click="onAskContinue(false)">结束问诊</button>
        </div>
      </div>
    </div>

    <!-- 错误弹层（含麦克风重试）-->
    <div v-if="state === 'error'" class="overlay-mask" role="dialog" aria-modal="true" aria-label="错误提示">
      <div class="overlay-card">
        <h2>{{ errorMsg }}</h2>
        <p v-if="errorNote">{{ errorNote }}</p>
        <div class="stack">
          <button type="button" class="btn-big primary" @click="onRetry">再试一次</button>
          <button v-if="micFail" type="button" class="btn-big secondary" @click="retryMic">重新尝试录音</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import StatusBanner from '@/components/StatusBanner.vue'
import { request, binaryAudioRequest } from '@/api/api.js'
import { consultSession, resetConsultation } from '@/store/session.js'
import { tts, beepOn, beepOff } from '@/lib/tts.js'
import { recorder } from '@/lib/recorder.js'

var router = useRouter()

var state = ref('idle')
var questionText = ref('')
var uploadHint = ref('')
var errorMsg = ref('')
var errorNote = ref('')
var micFail = ref(false)
var autoStopHint = ref(false)

// 2026-08-24 四项体验：进度 / 按住说话 / 等待暖话术
var stageNow = ref(0)
var STAGE_TOTAL = 8
var holdActive = ref(false)
var holdHint = ref('')
var holdStartTs = 0
var holdSec = ref(0)
var holdSecTimer = null
var barged = false
var PROCESSING_PHRASES = [
  '正在理解您的病情…',
  '正在查阅中医知识库…',
  '正在整理您的回答…',
  '马上就好，请稍候…',
]
var processingTimer = null
var processingIdx = 0

// Non-reactive working state
var currentQuestion = null
var lastAction = null // {type:'submit', payload} | {type:'replay'}
var silenceMs = 0
var lastRmsTs = 0
var silentReminders = 0
var interrupted = false
var finishedAttempted = false
var failureCount = 0
var networkRetries = 0

var SILENCE_RMS_THRESHOLD = 0.015
var SILENCE_LIMIT_MS = 15000
var MAX_SILENT_REMINDERS = 3
var HOLD_MIN_MS = 600

var bannerMap = {
  playing: { tone: 'playing', text: '正在提问' },
  'intro-ack': { tone: 'info', text: '请先了解说明' },
  listening: { tone: 'listening', text: '请您回答' },
  processing: { tone: 'processing', text: 'AI正在思考，请稍候' },
  finishing: { tone: 'playing', text: '问诊完成，正在收尾' },
  'ask-continue': { tone: 'processing', text: '先停一停' },
  error: { tone: 'processing', text: '出了点小状况' },
}

var bannerTone = computed(function () {
  var m = bannerMap[state.value]
  return m ? m.tone : 'info'
})

var bannerText = computed(function () {
  var m = bannerMap[state.value]
  return m ? m.text : ''
})

var pctWidth = computed(function () {
  var n = Math.min(stageNow.value, STAGE_TOTAL)
  return Math.round((n / STAGE_TOTAL) * 100) + '%'
})

var remainCount = computed(function () {
  return Math.max(STAGE_TOTAL - stageNow.value, 0)
})

function stateIsOneOf(list) {
  return list.indexOf(state.value) >= 0
}

onMounted(function () {
  if (!consultSession.ready) {
    router.replace('/patient?lost=1')
    return
  }
  document.addEventListener('visibilitychange', onVisibility)
  // 续问（当日同号复用）：跳过开场介绍，直接重放上一问
  if (consultSession.resumed) {
    playQuestion(consultSession.firstRound)
    return
  }
  // 开场介绍与【明白了】同屏（2026-08-24）：播报中即可直接点明白了解跳过
  state.value = 'intro-ack'
  questionText.value = (consultSession.firstRound && consultSession.firstRound.text) || ''
  tts.playStatic('OPENING').then(function (ok) {
    // 自然播毕保持 intro-ack（按钮已在屏上）；失败链路也已同屏
  }, function () {
    binaryAudioRequest('/api/patient/consultations/' + consultSession.sessionId + '/fixed-phrase-audio', {
      phrase_key: 'OPENING',
    }).then(function (r) { return tts.playBlob(r.blob) },
      function () { /* 无音频也保持同屏 */ })
  })
})

onBeforeUnmount(cleanupAll)

function enterIntroAck() {
  state.value = 'intro-ack'
  uploadHint.value = ''
  questionText.value = (consultSession.firstRound && consultSession.firstRound.text) || ''
}

function onIntroAck() {
  if (state.value !== 'intro-ack') return
  try { tts.stop() } catch (e) {}
  state.value = 'processing'
  questionText.value = ''
  uploadHint.value = PROCESSING_PHRASES[0]
  startHintRotation()
  var sid = consultSession.sessionId
  // 首问静态优先（瞬时，2026-08-24 v2.3）：/tts/FIRST_QUESTION.mp3
  tts.playStatic('FIRST_QUESTION').then(function (ok) {
    stopHintRotation()
    if (ok) {
      stageNow.value = 1
      playQuestion({ text: '', blob: null, staticKey: 'FIRST_QUESTION' })
      return
    }
    binaryAudioRequest('/api/patient/consultations/' + sid + '/ask', {})
      .then(function (r) {
        stopHintRotation()
        if (r.meta && r.meta.stage) stageNow.value = r.meta.stage
        playQuestion({ text: (r.meta && r.meta.text) || '', blob: r.blob })
      }, function () {
        stopHintRotation()
        showError('问题没有出来', '请点下面的按钮再试一次')
        lastAction = { type: 'replay' }
      })
  })
}

function replayIntro() {
  if (state.value !== 'intro-ack') return
  state.value = 'playing'
  tts.playStatic('OPENING').then(function (ok) {
    if (ok) { enterIntroAck(); return }
    binaryAudioRequest('/api/patient/consultations/' + consultSession.sessionId + '/fixed-phrase-audio', {
      phrase_key: 'OPENING',
    }).then(function (r) { return tts.playBlob(r.blob) })
      .then(enterIntroAck, enterIntroAck)
  }, enterIntroAck)
}

function playQuestion(q, isClosing) {
  // 静态优先：结束语走 /tts/CLOSING.mp3（文字同步）
  if (isClosing) {
    return tts.playStatic('CLOSING').then(function (ok) {
      questionText.value = (q && q.text) || '问诊完成，请您等候叫号就诊。'
      if (ok) return
      if (!q || !(q.audio_b64 || q.blob)) {
        showError('语音没有播出来', '请点下面的按钮再看看')
        return
      }
      return q.blob ? tts.playBlob(q.blob) : tts.play(q.audio_b64)
    })
  }
  var hasAudio = q && (q.audio_b64 || q.blob || q.audio_blob)
  if (!q || !hasAudio) {
    lastAction = { type: 'replay' }
    showError('问题内容加载失败', '请点下面的按钮重试')
    return
  }
  currentQuestion = q
  questionText.value = q.text
  uploadHint.value = ''
  state.value = 'playing'
  var pp = q.blob ? tts.playBlob(q.blob)
    : q.audio_blob ? tts.playBlob(q.audio_blob)
    : tts.play(q.audio_b64 || '')
  return pp.then(enterListening, onTtsError)
}

function onTtsError() {
  if (barged) { barged = false; return }  // 主动打断造成的停止不算错误
  // 语音播放失败（静音键/省电模式等）：手动重听出口（R4-B）
  lastAction = { type: 'replay' }
  showError('语音没有播出来', '可能是手机静音或省电模式，请调大音量后点下面的按钮再听一遍。')
}

function enterListening() {
  // 进入"按住说话"待命态：不自动开麦，等用户按下（W1: 手势栈内 begin_round）
  state.value = 'listening'
  silenceMs = 0
  lastRmsTs = nowMs()
}

function holdStart() {
  if (!stateIsOneOf(['playing', 'listening'])) return
  holdStartTs = nowMs()
  holdHint.value = ''
  // barge-in：播报中按下 → 立即停 TTS 转入聆听
  if (state.value === 'playing') {
    barged = true
    try { tts.stop() } catch (e) {}
    enterListening()
  }
  try {
    recorder.begin_round({
      onRms: onRms,
      onAutoStop: autoStopRound,
    })
    holdActive.value = true
    beepOn()
    try { if (navigator.vibrate) navigator.vibrate(30) } catch (e) {}
    uploadHint.value = ''
    holdSec.value = 0
    if (holdSecTimer) clearInterval(holdSecTimer)
    holdSecTimer = setInterval(function () {
      holdSec.value = Math.floor((nowMs() - holdStartTs) / 1000)
    }, 500)
  } catch (e) {
    micFail.value = true
    lastAction = { type: 'replay' }
    showError('无法启动录音', '请点下面的按钮重新尝试录音')
  }
}

function holdEnd() {
  if (!holdActive.value) return
  holdActive.value = false
  if (holdSecTimer) { clearInterval(holdSecTimer); holdSecTimer = null }
  beepOff()
  var held = nowMs() - holdStartTs
  if (held < HOLD_MIN_MS) {
    try { recorder.discard_round() } catch (e0) {}
    holdHint.value = '按的时间有点短，请按住按钮说话，说完松开'
    return
  }
  if (state.value === 'listening') finishSpeaking()
}

function nowMs() {
  return new Date().getTime()
}

function onRms(rms) {
  if (state.value !== 'listening') return
  var ts = nowMs()
  var dt = Math.min(ts - lastRmsTs, 500)
  lastRmsTs = ts
  if (rms < SILENCE_RMS_THRESHOLD) {
    silenceMs += dt
    if (silenceMs >= SILENCE_LIMIT_MS) triggerSilenceReminder()
  } else {
    silenceMs = 0
  }
}

function triggerSilenceReminder() {
  silenceMs = 0
  recorder.discard_round()
  silentReminders += 1
  holdActive.value = false
  if (silentReminders >= MAX_SILENT_REMINDERS) {
    state.value = 'ask-continue'
    return
  }
  state.value = 'processing'
  uploadHint.value = '没有听到您的声音哦，请听到提示后开口回答'
  tts.playStatic('REMINDER_SILENT').then(function (ok) {
    if (ok) {
      enterListening()
      return
    }
    binaryAudioRequest('/api/patient/consultations/' + consultSession.sessionId + '/fixed-phrase-audio', {
      phrase_key: 'REMINDER_SILENT',
    })
      .then(function (r) {
        return tts.playBlob(r.blob)
      })
      .then(enterListening, function () {
        enterListening()
      })
  })
}

function finishSpeaking() {
  if (state.value !== 'listening') return
  state.value = 'processing'
  startHintRotation()
  uploadHint.value = PROCESSING_PHRASES[0]
  recorder.stop().then(onRecorded, onRecordFailed)
}

function autoStopRound() {
  // 90s 上限：等同松开（区分提示，评审 F-R12）
  if (state.value === 'listening') {
    autoStopHint.value = true
    holdActive.value = false
    finishSpeaking()
  }
}

function onRecorded(result) {
  submitRound({
    audio_b64: result.audio_b64,
    duration_ms: result.duration_ms,
  })
}

function onRecordFailed() {
  stopHintRotation()
  showError('录音处理出现问题', '请点下面的按钮重新回答这个问题')
  lastAction = { type: 'replay' }
}

var stagedTimers = []

function submitRound(payload) {
  if (!payload.round_id) payload.round_id = genRoundId()
  lastAction = { type: 'submit', payload: payload }
  armStagedHints()
  var sid = consultSession.sessionId
  binaryAudioRequest('/api/patient/consultations/' + sid + '/rounds', payload)
    .then(handleRoundResponse, onRoundError)
    .finally(clearStagedTimers)
}

function genRoundId() {
  try {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID()
  } catch (e) {}
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 10)
}

function handleRoundResponse(resp) {
  failureCount = 0
  networkRetries = 0
  stopHintRotation() // 修复：下一问到达即停轮播，防残留
  var meta = resp.meta || resp
  var blob = resp.blob
  if (meta.stage) stageNow.value = Math.max(stageNow.value, meta.stage)
  if (meta.finished) {
    finishedAttempted = true
    stopHintRotation()
    state.value = 'finishing'
    questionText.value = ''
    currentQuestion = { text: meta.text, audio_b64: meta.audio_b64, blob: blob }
    playQuestion(currentQuestion, true).then(goDone, goDone)
    return
  }
  currentQuestion = { text: meta.text, audio_b64: meta.audio_b64, blob: blob }
  playQuestion(currentQuestion)
}

function onRoundError(e) {
  clearStagedTimers()
  stopHintRotation()
  var netCode = e && (e.code === 'NETWORK_TIMEOUT' || e.code === 'NETWORK_ERROR')
  if (netCode && networkRetries < 2 && lastAction && lastAction.type === 'submit') {
    networkRetries += 1
    var delay = networkRetries === 1 ? 1000 : 3000
    uploadHint.value = '网络有点慢，正在再试一次……'
    setTimeout(function () { submitRound(lastAction.payload) }, delay)
    return
  }
  networkRetries = 0
  if (e && e.code === 'CONSULT_SESSION_NOT_FOUND') {
    if (finishedAttempted) {
      goDone()
      return
    }
    sessionLost()
    return
  }
  failureCount += 1
  if (failureCount >= 3) {
    showError(
      '本次内容未能提交，不影响您正常就诊。',
      '您可以点下面的按钮再试一次，或者直接等候叫号。'
    )
  } else if (e && e.code === 'AUDIO_INVALID') {
    showError(e.message || '刚才没有听清', '请重新回答这个问题')
    lastAction = { type: 'replay' }
  } else {
    showError(
      e && e.message ? e.message : '网络不稳定，请重试',
      '刚才的回答还在，点下面的按钮再传一次就好'
    )
  }
}

function showError(title, note) {
  stopHintRotation()
  state.value = 'error'
  errorMsg.value = title
  errorNote.value = note || ''
}

function onRetry() {
  if (!lastAction) {
    sessionLost()
    return
  }
  if (lastAction.type === 'submit') {
    submitRound(lastAction.payload)
    return
  }
  playQuestion(currentQuestion)
}

function retryMic() {
  micFail.value = false
  recorder.warmup().then(function () {
    enterListening()
  }, function () {
    showError('还是没有听到麦克风', '请检查手机是否允许使用麦克风，然后点按钮再试一次')
  })
}

function replayQuestion() {
  if (stateIsOneOf(['listening'])) {
    try { recorder.discard_round() } catch (e) {}
    holdActive.value = false
    playQuestion(currentQuestion)
  }
}

function onAskContinue(keepGoing) {
  silentReminders = 0
  if (keepGoing) {
    playQuestion(currentQuestion)
  } else {
    forceFinish()
  }
}

function forceFinish() {
  state.value = 'processing'
  uploadHint.value = PROCESSING_PHRASES[0]
  startHintRotation()
  armStagedHints()
  var sid = consultSession.sessionId
  binaryAudioRequest('/api/patient/consultations/' + sid + '/rounds', {
    round_id: genRoundId(), force_finish: true,
  })
    .then(handleRoundResponse, onRoundError)
    .finally(clearStagedTimers)
}

// ===== 等待期暖话术轮播（2026-08-24 预期管理）=====
function startHintRotation() {
  stopHintRotation()
  processingIdx = 0
  uploadHint.value = PROCESSING_PHRASES[0]
  processingTimer = setInterval(function () {
    processingIdx += 1
    var list = PROCESSING_PHRASES
    if (processingIdx < list.length) {
      uploadHint.value = list[processingIdx]
    }
  }, 4000)
}

function stopHintRotation() {
  if (processingTimer) {
    clearInterval(processingTimer)
    processingTimer = null
  }
}

function armStagedHints() {
  clearStagedTimers()
  stagedTimers.push(setTimeout(function () {
    if (state.value === 'processing') {
      uploadHint.value = '前面有几个人也在咨询，请稍安勿躁'
    }
  }, 50000))
}

function clearStagedTimers() {
  for (var i = 0; i < stagedTimers.length; i++) clearTimeout(stagedTimers[i])
  stagedTimers = []
}

function goDone() {
  cleanupAll()
  resetConsultation()
  state.value = 'done-nav'
  router.replace('/patient/done')
}

function sessionLost() {
  cleanupAll()
  resetConsultation()
  router.replace('/patient?lost=1')
}

// 切后台：聆听中弃录；回前台重放当前问题（W5+）
function onVisibility() {
  if (document.hidden) {
    if (state.value === 'listening') {
      try { recorder.discard_round() } catch (e) {}
      holdActive.value = false
    }
    if (stateIsOneOf(['playing', 'listening', 'intro-ack'])) {
      tts.stop()
      interrupted = true
    }
    return
  }
  if (!interrupted) return
  interrupted = false
  if (stateIsOneOf(['playing', 'listening', 'intro-ack'])) {
    playQuestion(currentQuestion)
  }
}

function cleanupAll() {
  document.removeEventListener('visibilitychange', onVisibility)
  clearStagedTimers()
  stopHintRotation()
  try { recorder.cleanup() } catch (e) {}
  try { tts.stop() } catch (e) {}
}
</script>

<style scoped>
.progress {
  margin-top: var(--sp-4);
  padding: var(--sp-4);
}

.progress-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--sp-2);
}

.progress-label {
  font-size: var(--fs-small);
  color: var(--c-muted);
}

.progress-num {
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--c-primary);
}

.progress-bar {
  height: 14px;
  background: #e8efe9;
  border-radius: 7px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--c-primary);
  border-radius: 7px;
  transition: width 0.5s ease;
}

.progress-note {
  font-size: var(--fs-small);
  color: var(--c-muted);
  margin: var(--sp-2) 0 0;
}

.q-card {
  margin-top: var(--sp-4);
}

.q-label {
  font-size: var(--fs-small);
  color: var(--c-muted);
  margin: 0 0 var(--sp-2);
}

.q-text {
  font-size: var(--fs-big);
  line-height: 1.5;
  margin: 0;
}

.controls {
  margin-top: var(--sp-6);
}

.hold-btn {
  width: 100%;
  min-height: 96px;
  font-size: var(--fs-title);
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}

.hold-btn.holding {
  background: var(--c-primary-dark, #0a4f2d);
  transform: scale(0.98);
}

.controls .btn-mid {
  width: 100%;
  margin-top: var(--sp-4);
}
</style>
