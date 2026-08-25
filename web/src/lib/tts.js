/**
 * TtsPlayer: element-level unlock TTS player (R4 red line W5).
 *
 * - One <audio> element created at construction.
 * - unlock() MUST run synchronously inside the user gesture
 *   (confirm button click): plays a 0.2s silent WAV through this exact
 *   element once; afterwards the element can be played programmatically
 *   for the whole session.
 * - play(b64) resolves on ended + watchdog double check.
 */

function makeSilentWavUrl() {
  var sampleRate = 8000
  var dataLen = Math.round(sampleRate * 0.2) * 2
  var buf = new ArrayBuffer(44 + dataLen)
  var v = new DataView(buf)
  function wstr(off, s) {
    for (var k = 0; k < s.length; k++) v.setUint8(off + k, s.charCodeAt(k))
  }
  wstr(0, 'RIFF')
  v.setUint32(4, 36 + dataLen, true)
  wstr(8, 'WAVE')
  wstr(12, 'fmt ')
  v.setUint32(16, 16, true)
  v.setUint16(20, 1, true)
  v.setUint16(22, 1, true)
  v.setUint32(24, sampleRate, true)
  v.setUint32(28, sampleRate * 2, true)
  v.setUint16(32, 2, true)
  v.setUint16(34, 16, true)
  wstr(36, 'data')
  v.setUint32(40, dataLen, true)
  return 'data:audio/wav;base64,' + bytesToB64(new Uint8Array(buf))
}

function bytesToB64(u8) {
  var bin = ''
  var CH = 0x8000
  for (var i = 0; i < u8.length; i += CH) {
    bin += String.fromCharCode.apply(null, u8.subarray(i, i + CH))
  }
  return btoa(bin)
}

function b64ToBlobUrl(b64) {
  var raw = window.atob(b64)
  var len = raw.length
  var u8 = new Uint8Array(len)
  for (var i = 0; i < len; i++) u8[i] = raw.charCodeAt(i)
  var blob = new Blob([u8], { type: 'audio/wav' })
  return URL.createObjectURL(blob)
}

export class TtsPlayError extends Error {
  constructor(msg) {
    super(msg || '语音播放失败')
    this.name = 'TtsPlayError'
    this.isTtsError = true
  }
}

export class TtsPlayer {
  constructor() {
    this.audio = null
    this.currentUrl = null
    this.unlocked = false
    this._watchdog = null
  }

  _ensureAudio() {
    if (this.audio) return
    var el = document.createElement('audio')
    el.preload = 'none'
    el.autoplay = false
    this.audio = el
  }

  unlock() {
    if (this.unlocked) return
    this._ensureAudio()
    var el = this.audio
    try {
      el.src = makeSilentWavUrl()
      el.load()
      var p = el.play()
      if (p && p.catch) {
        p.catch(function () {
          // 解锁重试一次（部分 iOS 首次 play 仍需手势内二次触发）
          try {
            var p2 = el.play()
            if (p2 && p2.catch) p2.catch(function () {})
          } catch (e2) {}
        })
      }
      this.unlocked = true
    } catch (e) {
      /* best effort */
    }
  }

  stop() {
    if (!this.audio) return
    try { this.audio.pause() } catch (e) {}
  }

  play(b64) {
    var self = this
    return new Promise(function (resolve, reject) {
      self._ensureAudio()
      var el = self.audio
      self._teardownWatchdog()
      self._teardownCurrentUrl()
      var url = b64ToBlobUrl(b64)
      self._setSrcAndPlay(url, resolve, reject)
    })
  }

  playBlob(blob) {
    // 二进制直传入口（带宽优化：mp3 原始字节直接播，省 3/4 流量）。
    // 复用 playUrl-同一播放闭环（含解锁、卡死看门狗、自动重试）。
    var url = URL.createObjectURL(blob)
    return this.playUrl(url)
  }
  playUrl(url) {
    var self = this
    return new Promise(function (resolve, reject) {
      self._ensureAudio()
      self._teardownWatchdog()
      self._teardownCurrentUrl()
      self._setSrcAndPlay(url, resolve, reject)
    })
  }

  _teardownCurrentUrl() {
    if (this.currentUrl) {
      URL.revokeObjectURL(this.currentUrl)
      this.currentUrl = null
    }
  }

  _setSrcAndPlay(url, resolve, reject) {
    var self = this
    var el = self.audio
    var done = false
    function cleanup() {
      el.removeEventListener('ended', finish)
      el.removeEventListener('error', fail)
    }
    function finish() {
      if (done) return
      done = true
      self._teardownWatchdog()
      cleanup()
      resolve()
    }
    function fail() {
      if (done) return
      done = true
      self._teardownWatchdog()
      cleanup()
      reject(new TtsPlayError())
    }
    el.addEventListener('ended', finish)
    el.addEventListener('error', fail)
    var startedAt = Date.now()
    var watch = setInterval(function () {
      try {
        var elapsed = Date.now() - startedAt
        if (elapsed > 3000 && el.currentTime === 0) {
          // 卡死看门狗（评审 F-R7）：3s 后仍停在 0 秒判定播放失败
          fail()
          return
        }
        if (!el.paused && el.duration > 0 && el.currentTime >= el.duration - 0.08) finish()
      } catch (e) {}
    }, 500)
    self._watchdog = watch
    el.src = url
    self.currentUrl = url
    el.load()
    var p = el.play()
    if (p && p.catch) {
      p.catch(function () {
        if (done) return
        // 自动重试一次播放（解锁后重试通常成功）——用户要求"自动发声"
        try {
          var p2 = el.play()
          if (p2 && p2.catch) p2.catch(function () { fail() })
        } catch (e2) {
          fail()
        }
      })
    }
  }

  _teardownWatchdog() {
    if (this._watchdog) {
      clearInterval(this._watchdog)
      this._watchdog = null
    }
  }

  // 固定话术静态优先：直接播放尝试（无 HEAD 探测——避免 fetch HEAD 永不落定导致白屏）
  // 失败经 audio error 事件立即触发回退，由调用方走动态接口兜底
  playStatic(key) {
    var self = this
    var miss = this.__staticMisses || (this.__staticMisses = {})
    if (miss[key]) return Promise.resolve(false)
    function attempt(url) {
      return self.playUrl(url).then(
        function () { return true },
        function () { return self.playUrlFallback(url) }
      )
    }
    // 404/解码失败的 audio error 会快速 reject；此处补一个兜底序列
    return this._playStaticSeq(key, ['/tts/' + key + '.mp3', '/tts/' + key + '.wav'])
  }

  _playStaticSeq(key, urls) {
    var self = this
    if (!urls.length) {
      self.__staticMisses[key] = true
      return Promise.resolve(false)
    }
    var u = urls[0]
    return self.playUrl(u).then(function () { return true },
      function () { return self._playStaticSeq(key, urls.slice(1)) })
  }


}

export var tts = new TtsPlayer()


// ===== 按住说话提示音（微信式"哒"）=====
// 独立 audio 元素：touchstart/touchend 本身是手势，新元素当场解锁合法
var _beepEl = null

function _playBeepFile(url) {
  try {
    if (!_beepEl) _beepEl = new Audio()
    _beepEl.src = url
    _beepEl.play().catch(function () {})
  } catch (e) {}
}

export function beepOn() {
  _playBeepFile('/tts/beep_on.wav')
}

export function beepOff() {
  _playBeepFile('/tts/beep_off.wav')
}


// ===== 快捷语音：按键音/数字核对序列（独立元素，手势内解锁）=====
var _quickEl = null
var _seqEl = null

export function speakUrl(url) {
  // 单条即时播报（打断上一次）
  try {
    if (!_quickEl) _quickEl = new Audio()
    _quickEl.src = url
    var pr = _quickEl.play()
    if (pr && pr.catch) pr.catch(function () {})
  } catch (e) {}
}

export function speakUrls(urls) {
  // 顺序播报（前一条 ended 后播下一条）
  return new Promise(function (resolve) {
    try {
      if (!_seqEl) _seqEl = new Audio()
      var el = _seqEl
      var i = 0
      function next() {
        if (i >= urls.length) { el.removeEventListener('ended', next); resolve(); return }
        el.src = urls[i]
        el.load()
        var pr = el.play()
        i += 1
        if (pr && pr.catch) pr.catch(function () { next() })
        el.addEventListener('ended', next, { once: true })
      }
      next()
    } catch (e) { resolve() }
  })
}
