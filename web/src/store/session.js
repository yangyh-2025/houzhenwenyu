/**
 * In-memory consult session store.
 *
 * Deliberately NOT persisted (privacy: nothing beyond the four whitelisted
 * fields ever lands on disk; refresh = mid-way exit per PRD F3-R13).
 * Refresh loses the session -> patient re-scans QR code and restarts.
 */

import { reactive } from 'vue'

export const consultSession = reactive({
  ready: false,
  visitNumber: '',
  sessionId: '',
  roundsLimit: 10,
  firstRound: null, // {text, audio_b64}
})

export function setConsultation(createResp, visitNumber) {
  consultSession.ready = true
  consultSession.visitNumber = visitNumber
  consultSession.sessionId = createResp.session_id
  consultSession.roundsLimit = createResp.rounds_limit || 10
  consultSession.firstRound = createResp.first_round || null
}

export function resetConsultation() {
  consultSession.ready = false
  consultSession.visitNumber = ''
  consultSession.sessionId = ''
  consultSession.roundsLimit = 10
  consultSession.firstRound = null
}
