/**
 * Browser-side capture for MeetScribe "Record from this browser" mode.
 *
 * Runs on whichever laptop you're sitting at, and streams audio to the PC that
 * does the Whisper + Ollama work. Deliberately cheap on CPU: the only real work
 * is MediaRecorder's Opus encoder, which is hardware-backed, so a slow laptop
 * can handle it while also running Google Meet.
 *
 * Two sources are captured and kept on SEPARATE channels:
 *   left  = your microphone      (getUserMedia)
 *   right = the meeting audio    (getDisplayMedia on the Meet tab)
 *
 * They stay separate all the way to the server so the same audio-health check
 * the local recorder uses can tell "the meeting audio never arrived" apart from
 * "nobody spoke". The server mixes them 50/50 after judging them.
 *
 * Requires a secure context (https:// or localhost) — browsers will not hand
 * over a microphone or a tab otherwise.
 */

const CHUNK_MS = 3000

export function isCaptureSupported() {
  return !!(
    window.isSecureContext &&
    navigator.mediaDevices?.getUserMedia &&
    navigator.mediaDevices?.getDisplayMedia &&
    window.MediaRecorder
  )
}

export function unsupportedReason() {
  if (!window.isSecureContext) {
    return 'This page must be opened over https:// for the browser to allow audio capture.'
  }
  if (!navigator.mediaDevices?.getDisplayMedia) {
    return 'This browser cannot capture tab audio. Use Chrome or Edge on a desktop.'
  }
  if (!window.MediaRecorder) {
    return 'This browser does not support MediaRecorder.'
  }
  return null
}

export class BrowserCapture {
  constructor({ onLevels, onError, onUploadedBytes } = {}) {
    this.onLevels = onLevels
    this.onError = onError
    this.onUploadedBytes = onUploadedBytes

    this.meetingId = null
    this.micStream = null
    this.displayStream = null
    this.ctx = null
    this.recorder = null
    this.levelTimer = null

    // Chunks must reach the server in order — a WebM stream is only decodable
    // if its byte sequence is intact — so uploads are chained, never parallel.
    this.uploadChain = Promise.resolve()
    this.uploadedBytes = 0
    this.failed = false
  }

  async start({ meetingName, micDeviceId }) {
    const reason = unsupportedReason()
    if (reason) throw new Error(reason)

    // Ask for the meeting tab first. It is the step most likely to be
    // cancelled, and doing it first means we don't hold an open mic if it is.
    this.displayStream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    })

    if (this.displayStream.getAudioTracks().length === 0) {
      this.cleanup()
      throw new Error(
        'No tab audio was shared. Pick the Google Meet tab and turn ON "Also share tab audio" before sharing.'
      )
    }

    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: micDeviceId ? { exact: micDeviceId } : undefined,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })

    // Tell the server a session is starting only once both permissions are
    // granted, so a cancelled picker never leaves an empty recording behind.
    const res = await fetch('/api/remote/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ meeting_name: meetingName }),
    })
    const data = await res.json()
    if (!data.success) {
      this.cleanup()
      throw new Error(data.error || 'Could not start the remote session')
    }
    this.meetingId = data.id

    this.buildGraph()
    this.startRecorder()

    // If you press Chrome's own "Stop sharing" button, end the meeting cleanly
    // rather than silently recording a dead channel for the rest of the call.
    this.displayStream.getVideoTracks()[0]?.addEventListener('ended', () => {
      this.onError?.('Tab sharing was stopped from the browser. Finishing the recording…')
      this.requestStop?.()
    })

    return this.meetingId
  }

  buildGraph() {
    this.ctx = new AudioContext()
    const micSrc = this.ctx.createMediaStreamSource(this.micStream)
    const sysSrc = this.ctx.createMediaStreamSource(this.displayStream)

    this.micAnalyser = this.ctx.createAnalyser()
    this.sysAnalyser = this.ctx.createAnalyser()
    this.micAnalyser.fftSize = 512
    this.sysAnalyser.fftSize = 512
    micSrc.connect(this.micAnalyser)
    sysSrc.connect(this.sysAnalyser)

    // Merge to a 2-channel stream: mic left, meeting audio right.
    const merger = this.ctx.createChannelMerger(2)
    micSrc.connect(merger, 0, 0)
    sysSrc.connect(merger, 0, 1)

    this.dest = this.ctx.createMediaStreamDestination()
    this.dest.channelCount = 2
    merger.connect(this.dest)

    this.startLevelMeter()
  }

  startLevelMeter() {
    const micBuf = new Float32Array(this.micAnalyser.fftSize)
    const sysBuf = new Float32Array(this.sysAnalyser.fftSize)
    const rms = (buf) => {
      let sum = 0
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
      return Math.sqrt(sum / buf.length)
    }
    this.levelTimer = setInterval(() => {
      this.micAnalyser.getFloatTimeDomainData(micBuf)
      this.sysAnalyser.getFloatTimeDomainData(sysBuf)
      this.onLevels?.({ mic: rms(micBuf), system: rms(sysBuf) })
    }, 250)
  }

  startRecorder() {
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'

    this.recorder = new MediaRecorder(this.dest.stream, {
      mimeType,
      audioBitsPerSecond: 128000,
    })

    this.recorder.ondataavailable = (e) => {
      if (!e.data || e.data.size === 0 || this.failed) return
      this.uploadChain = this.uploadChain.then(() => this.upload(e.data))
    }

    this.recorder.start(CHUNK_MS)
  }

  async upload(blob) {
    try {
      const res = await fetch(`/api/remote/chunk?id=${encodeURIComponent(this.meetingId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: blob,
      })
      if (!res.ok) throw new Error(`Upload failed (${res.status})`)
      const data = await res.json()
      this.uploadedBytes = data.bytes ?? this.uploadedBytes
      this.onUploadedBytes?.(this.uploadedBytes)
    } catch (e) {
      // A dropped Wi-Fi packet mid-meeting shouldn't kill the recording, but a
      // gap in a WebM stream is unrecoverable, so surface it immediately.
      this.failed = true
      this.onError?.(`Lost connection to MeetScribe: ${e.message}`)
    }
  }

  async stop() {
    if (this.recorder && this.recorder.state !== 'inactive') {
      const flushed = new Promise((resolve) => {
        this.recorder.onstop = resolve
      })
      this.recorder.stop()
      await flushed
    }
    // Let every queued chunk land before telling the server to finalize.
    await this.uploadChain

    this.cleanup()

    const res = await fetch('/api/remote/finalize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: this.meetingId }),
    })
    const data = await res.json()
    if (!data.success) throw new Error(data.error || 'Could not finalize the recording')
    return data.meeting
  }

  async cancel() {
    try {
      if (this.recorder && this.recorder.state !== 'inactive') this.recorder.stop()
    } catch {}
    this.cleanup()
    if (this.meetingId) {
      await fetch('/api/remote/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: this.meetingId }),
      }).catch(() => {})
    }
  }

  cleanup() {
    clearInterval(this.levelTimer)
    this.levelTimer = null
    this.micStream?.getTracks().forEach(t => t.stop())
    this.displayStream?.getTracks().forEach(t => t.stop())
    this.micStream = null
    this.displayStream = null
    try { this.ctx?.close() } catch {}
    this.ctx = null
  }
}
