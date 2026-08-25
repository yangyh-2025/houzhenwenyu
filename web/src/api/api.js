/**
 * Unified API client.
 *
 * - Same-origin base '' with credentials:'same-origin' (cookie auth).
 * - AbortController timeout: 30s patient / 8s doctor endpoints.
 * - Error envelope {code,message,trace_id} -> ApiError{code,message,status}.
 */

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message)
    this.name = 'ApiError'
    this.code = code || 'UNKNOWN'
    this.message = message || '请求没有成功，请重试'
    this.status = status || 0
  }
}

function pickTimeout(path) {
  // 患者端 75s：20 并发排队+AI合成裕量（nginx 90s / 服务端 55s 阶梯）
  if (path.indexOf('/api/doctor') === 0) return 8000
  return 75000
}

export function request(path, opts) {
  opts = opts || {}
  var method = opts.method || 'GET'
  var body = opts.body
  var timeoutMs = opts.timeoutMs || pickTimeout(path)
  var ctrl = new AbortController()
  var timer = setTimeout(function () {
    ctrl.abort()
  }, timeoutMs)

  return fetch(path, {
    method: method,
    credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: ctrl.signal,
  })
    .then(function (resp) {
      clearTimeout(timer)
      if (resp.status === 204) return null
      return resp
        .json()
        .catch(function () { return null })
        .then(function (data) {
          if (!resp.ok) {
            if (resp.status === 401 && path.indexOf('/api/doctor') === 0) {
              // 会话过期/未登录：清态回登录页（PRD F6-AC4；评审 F-R2）
              try { sessionStorage.removeItem('hwy_doc_user') } catch (e0) {}
              var login = '/doctor/login'
              if (location.pathname !== login) location.replace(login)
            }
            throw new ApiError(
              data && data.code,
              (data && data.message) || '请求没有成功，请重试',
              resp.status
            )
          }
          return data
        })
    })
    .catch(function (e) {
      clearTimeout(timer)
      if (e instanceof ApiError) throw e
      var aborted = e && e.name === 'AbortError'
      if (aborted) {
        throw new ApiError('NETWORK_TIMEOUT', '网络有点慢，刚才没有成功，请再试一次', 0)
      }
      throw new ApiError('NETWORK_ERROR', '网络不稳定，请检查网络后重试', 0)
    })
}


// 二进制音频直传（带宽优化）：Accept audio/* → 原始 body + X-Hwy-Meta 头。
// 元数据为 ASCII 转义 JSON；audio 为 mp3/wav 原始字节，不经 base64 膨胀。
export function binaryAudioRequest(path, body) {
  var timeoutMs = pickTimeout(path)
  var ctrl = new AbortController()
  var timer = setTimeout(function () { ctrl.abort() }, timeoutMs)
  return fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'audio/mpeg, audio/wav, audio/*;q=0.9',
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: ctrl.signal,
  })
    .then(function (resp) {
      clearTimeout(timer)
      if (!resp.ok) {
        return resp
          .json()
          .catch(function () { return null })
          .then(function (data) {
            throw new ApiError(
              data && data.code,
              (data && data.message) || '请求没有成功，请重试',
              resp.status
            )
          })
      }
      var metaRaw = resp.headers.get('X-Hwy-Meta') || '{}'
      var meta = {}
      try { meta = JSON.parse(metaRaw) } catch (e) {}
      return resp.arrayBuffer().then(function (buf) {
        return { meta: meta, blob: new Blob([buf]) }
      })
    })
    .catch(function (e) {
      clearTimeout(timer)
      if (e instanceof ApiError) throw e
      if (e && e.name === 'AbortError') {
        throw new ApiError('NETWORK_TIMEOUT', '网络有点慢，刚才没有成功，请再试一次', 0)
      }
      throw new ApiError('NETWORK_ERROR', '网络不稳定，请检查网络后重试', 0)
    })
}
