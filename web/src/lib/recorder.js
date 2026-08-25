/**
 * VoiceRecorder: warmed-stream PCM capture (R4 W1 variant + W2/W3).
 *
 * - warmup() MUST be called inside a user gesture: getUserMedia + AudioContext
 *   creation/resume. The stream is held open for the whole session so later
 *   rounds can start capture outside any gesture (W1 "pre-warmed stream").
 * - begin_round() starts ScriptProcessor collection (W2), 90s auto-stop,
 *   per-buffer RMS callback for silence detection.
 * - stop() encodes 16kHz mono PCM16 WAV (W3) and returns {audio_b64,duration_ms}.
 * - discard_round() drops current capture (silence reminder / backgrounding).
 * - cleanup() full teardown.
 */

var TARGET_SR = 16000

function downsample(f32, fromRate, toRate) {
  if (fromRate === toRate) return f32
  var ratio = fromRate / toRate
  var outLen = Math.round(f32.length / ratio)
  var out = new Float32Array(outLen)
  for (var i = 0; i < outLen; i++) {
    var pos = i * ratio
    var i0 = Math.floor(pos)
    var frac = pos - i0
    var s0 = f32[i0]
    var s1 = f32[Math.min(i0 + 1, f32.length - 1)]
    out[i] = s0 + (s1 - s0) * frac
  }
  return out
}

function encodeWav(f32, sampleRate) {
  var len = f32.length
  var buf = new ArrayBuffer(44 + len * 2)
  var v = new DataView(buf)
  function wstr(off, s) {
    for (var k = 0; k < s.length; k++) v.setUint8(off + k, s.charCodeAt(k))
  }
  wstr(0, 'RIFF')
  v.setUint32(4, 36 + len * 2, true)
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
  v.setUint32(40, len * 2, true)
  for (var i = 0; i < len; i++) {
    var s = f32[i]
    if (s > 1) s = 1
    if (s < -1) s = -1
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Uint8Array(buf)
}

function bytesToB64(u8) {
  var bin = ''
  var CH = 0x8000
  for (var i = 0; i < u8.length; i += CH) {
    bin += String.fromCharCode.apply(null, u8.subarray(i, i + CH))
  }
  return btoa(bin)
}

export class VoiceRecorder {
  constructor() {
    this.stream = null
    this.ctx = null
    this._collecting = false
    this._chunks = []
    this._total = 0
    this._autoTimer = null
    this._onRms = null
    this._source = null
    this._processor = null
    this._mute = null
  }

  warmup() {
    var self = this
    if (this.stream && this.ctx) {
      return this.ctx.resume().catch(function () {})
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.reject(new Error('UNSUPPORTED'))
    }
    return navigator.mediaDevices
      .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      .then(function (stream) {
        self.stream = stream
        var AC = window.AudioContext || window.webkitAudioContext
        if (!AC) throw new Error('UNSUPPORTED')
        self.ctx = new AC()
        return self.ctx.resume().catch(function () {})
      })
      .catch(function (e) {
        if (e && e.name === 'NotAllowedError') e.isPermissionError = true
        throw e
      })
  }

  _detach() {
    try { if (this._processor) this._processor.onaudioprocess = null } catch (e) {}
    try { if (this._processor) this._processor.disconnect() } catch (e) {}
    try { if (this._source) this._source.disconnect() } catch (e) {}
    try { if (this._mute) this._mute.disconnect() } catch (e) {}
    this._source = null
    this._processor = null
    this._mute = null
  }

  begin_round(opts) {
    opts = opts || {}
    var self = this
    if (!this.stream || !this.ctx) throw new Error('NOT_WARMED')
    // iOS：流被系统回收时轨道失效 → 抛错由上层引导重新授权
    var live = this.stream.getTracks().every(function (t) {
      return t.readyState === 'live'
    })
    if (!live) {
      this.stream = null
      throw new Error('MIC_STREAM_DEAD')
    }
    if (this._collecting) this.discard_round()
    if (this.ctx.state === 'suspended') {
      this.ctx.resume().catch(function () {})
    }
    this._chunks = []
    this._total = 0
    this._onRms = opts.onRms || null
    this._autoStop = opts.onAutoStop || null
    this._source = this.ctx.createMediaStreamSource(this.stream)
    this._processor = this.ctx.createScriptProcessor(4096, 1, 1)
    this._mute = this.ctx.createGain()
    this._mute.gain.value = 0
    this._processor.onaudioprocess = function (ev) {
      var input = ev.inputBuffer.getChannelData(0)
      self._chunks.push(new Float32Array(input))
      self._total += input.length
      if (self._onRms) {
        var sum = 0
        for (var i = 0; i < input.length; i++) {
          sum += input[i] * input[i]
        }
        self._onRms(Math.sqrt(sum / input.length))
      }
    }
    this._source.connect(this._processor)
    this._processor.connect(this._mute)
    this._mute.connect(this.ctx.destination)
    this._collecting = true
    this._autoTimer = setTimeout(function () {
      if (self._autoStop) self._autoStop()
    }, 90000)
  }

  stop() {
    var self = this
    return new Promise(function (resolve, reject) {
      if (!self._collecting) {
        reject(new Error('NOT_COLLECTING'))
        return
      }
      var sr = self.ctx.sampleRate
      self._detach()
      clearTimeout(self._autoTimer)
      self._collecting = false
      var merged = new Float32Array(self._total)
      var off = 0
      for (var i = 0; i < self._chunks.length; i++) {
        merged.set(self._chunks[i], off)
        off += self._chunks[i].length
      }
      var duration_ms = Math.round((self._total / sr) * 1000)
      var pcm = downsample(merged, sr, TARGET_SR)
      resolve({ audio_b64: bytesToB64(encodeWav(pcm, TARGET_SR)), duration_ms: duration_ms })
    })
  }

  discard_round() {
    if (!this._collecting) return
    clearTimeout(this._autoTimer)
    this._detach()
    this._collecting = false
    this._chunks = []
    this._total = 0
  }

  cleanup() {
    this.discard_round()
    if (this.stream) {
      var tracks = this.stream.getTracks()
      for (var i = 0; i < tracks.length; i++) tracks[i].stop()
      this.stream = null
    }
    if (this.ctx) {
      var c = this.ctx
      this.ctx = null
      c.close().catch(function () {})
    }
  }
}

export var recorder = new VoiceRecorder()
