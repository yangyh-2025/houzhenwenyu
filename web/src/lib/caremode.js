/**
 * 微信关怀模式/大字号跟随适配（R4 §2.4，红线 W6）
 *
 * 策略：
 * 1. 先锁微信默认缩放：setFontSizeCallback fontSize:'2'（默认档），
 *    防止微信默认缩放与页面字号叠加失控。
 * 2. 再监听 menu:setfont，按 fontScale 重设根字号 —— 跟随放大而非对抗。
 * 3. 文字尺寸全部走 rem/clamp（见 tokens.css），间距用 px 固定不随字号缩放
 *   （微信支付 H5 收银台适老化字体规范细则）。
 */

var inited = false

function parseScale(raw) {
  if (typeof raw !== 'string') return null
  var m = raw.match(/(\d+(?:\.\d+)?)/)
  if (!m) return null
  var n = parseFloat(m[1])
  if (!isFinite(n) || n < 0.8 || n > 3) return null
  return n
}

export function initCareMode() {
  if (inited) return
  inited = true

  var docEl = document.documentElement

  function applyScale(scale) {
    var s = Math.min(Math.max(scale, 1), 2)
    docEl.style.fontSize = 16 * s + 'px'
  }

  function onBridgeReady() {
    try {
      var bridge = window.WeixinJSBridge
      if (!bridge || !bridge.invoke || !bridge.on) return
      bridge.invoke('setFontSizeCallback', { fontSize: '2' }, function () {})
      bridge.on('menu:setfont', function (res) {
        var scale = parseScale(res && res.fontScale)
        if (!scale && res && typeof res.fontSize === 'string') {
          // fontSize 档位字符串（如 "4"）时按档位近似换算
          var level = parseFloat(res.fontSize)
          if (isFinite(level)) {
            applyScale(1 + (level - 2) * 0.15)
            return
          }
        }
        if (scale) applyScale(scale)
      })
    } catch (e) {
      /* 非 WeChat 环境：忽略 */
    }
  }

  if (window.WeixinJSBridge && window.WeixinJSBridge.on) {
    onBridgeReady()
  } else {
    document.addEventListener('WeixinJSBridgeReady', onBridgeReady, false)
  }
}
