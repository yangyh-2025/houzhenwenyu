/**
 * Environment detection (F5 iOS+WeChat guidance banner).
 * Evaluated once at module load; static environment facts only.
 */

var ua = navigator.userAgent || ''

var isApple = /iPad|iPhone|iPod/.test(ua) ||
  (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)

var isWeChat = /MicroMessenger/i.test(ua)

// F5: Apple device + WeChat in-app browser -> persistent banner.
// Fallback: mediaDevices missing (non-HTTPS or old kernel) -> same banner.
var noMediaDevices = !(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)

export var needsSafariGuide = (isApple && isWeChat) || noMediaDevices
