import { useState, useEffect, useRef } from 'react'
import { Mic, Volume2, Square, Circle, Loader2, Server, Laptop } from 'lucide-react'
import { BrowserCapture, isCaptureSupported, unsupportedReason } from '../browserCapture'

export default function Recorder({ status, devices, onStart, onStop, onBrowserStart, onBrowserStop }) {
  const [meetingName, setMeetingName] = useState('')
  const [micDevice, setMicDevice] = useState('')
  const [error, setError] = useState('')
  const [liveData, setLiveData] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [startWarning, setStartWarning] = useState(null)

  // Mode B — capture in this browser instead of on the server. Used when the
  // meeting is on the machine you're looking at, not the one running Whisper.
  const [mode, setMode] = useState('server') // 'server' | 'browser'
  const [browserMics, setBrowserMics] = useState([])
  const [browserMic, setBrowserMic] = useState('')
  const [levels, setLevels] = useState({ mic: 0, system: 0 })
  const [uploaded, setUploaded] = useState(0)

  const captureRef = useRef(null)
  const liveRef = useRef(null)
  const timerRef = useRef(null)
  const startTimeRef = useRef(null)

  const isRecording = status === 'recording'
  const isTranscribing = status === 'transcribing'
  const isBusy = isRecording || isTranscribing

  useEffect(() => {
    if (!devices.length) return
    const mics = devices.filter(d => !d.is_loopback)
    if (mics.length && !micDevice) setMicDevice(String(mics[0].index))
  }, [devices])

  // The mics that matter in browser mode belong to THIS laptop, not the server,
  // so they come from the browser rather than /api/devices. Labels stay blank
  // until the user grants mic permission once — the default entry still works.
  const loadBrowserMics = async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices()
      setBrowserMics(all.filter(d => d.kind === 'audioinput'))
    } catch {}
  }

  useEffect(() => {
    if (mode === 'browser' && isCaptureSupported()) loadBrowserMics()
  }, [mode])

  useEffect(() => {
    if (isRecording) {
      startTimeRef.current = Date.now()
      setElapsed(0)
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000))
      }, 1000)
      // Only the server-side recorder has a live_status endpoint to poll;
      // browser mode measures its own levels locally in the audio graph.
      if (mode === 'server') {
        liveRef.current = setInterval(async () => {
          try {
            const d = await fetch('/api/live_status').then(r => r.json())
            setLiveData(d)
          } catch {}
        }, 1000)
      }
    } else {
      clearInterval(timerRef.current)
      clearInterval(liveRef.current)
      setLiveData(null)
      setElapsed(0)
      setStartWarning(null)
      startTimeRef.current = null
    }
    return () => {
      clearInterval(timerRef.current)
      clearInterval(liveRef.current)
    }
  }, [isRecording])

  const formatTime = (s) => {
    const h = String(Math.floor(s / 3600)).padStart(2, '0')
    const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
    const sec = String(s % 60).padStart(2, '0')
    return `${h}:${m}:${sec}`
  }

  const handleStart = async () => {
    setError('')
    if (!meetingName.trim()) { setError('Please enter a meeting name.'); return }
    setStartWarning(null)

    if (mode === 'browser') {
      const reason = unsupportedReason()
      if (reason) { setError(reason); return }
      try {
        const capture = new BrowserCapture({
          onLevels: setLevels,
          onUploadedBytes: setUploaded,
          onError: (msg) => setError(msg),
        })
        capture.requestStop = () => handleStop()
        captureRef.current = capture
        setUploaded(0)
        await capture.start({
          meetingName: meetingName.trim(),
          micDeviceId: browserMic || undefined,
        })
        onBrowserStart()
        loadBrowserMics() // labels are readable now that permission was granted
      } catch (e) {
        captureRef.current = null
        // A cancelled share picker is a normal action, not an error worth shouting about.
        setError(e.name === 'NotAllowedError'
          ? 'Screen/mic permission was denied or the picker was cancelled.'
          : e.message)
      }
      return
    }

    try {
      const data = await onStart({
        meetingName: meetingName.trim(),
        micDevice: micDevice !== '' ? parseInt(micDevice) : null,
      })
      setStartWarning(data?.warning || null)
    } catch (e) { setError(e.message) }
  }

  const handleStop = async () => {
    setError('')
    if (mode === 'browser') {
      const capture = captureRef.current
      if (!capture) return
      captureRef.current = null
      try {
        await capture.stop()
        onBrowserStop()
        setMeetingName('')
      } catch (e) { setError(e.message); onBrowserStop() }
      return
    }
    try { await onStop(); setMeetingName('') }
    catch (e) { setError(e.message) }
  }

  const mics = devices.filter(d => !d.is_loopback)

  const chevron = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E")`

  return (
    <div style={{ background: '#fff', border: '1px solid #d1d5db', borderRadius: '16px', boxShadow: '0 4px 16px rgba(0,0,0,0.08)', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #e5e7eb', background: 'linear-gradient(135deg, #eef2ff 0%, #f8fafc 100%)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <p style={{ fontWeight: 700, fontSize: '15px', color: '#111827', margin: 0 }}>New Recording</p>
          <p style={{ fontSize: '12px', color: '#6b7280', margin: '2px 0 0' }}>Capture your mic and system audio together</p>
        </div>
        {isTranscribing && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 600, color: '#92400e', background: '#fef3c7', border: '1px solid #fcd34d', borderRadius: '99px', padding: '5px 12px' }}>
            <Loader2 size={12} className="animate-spin" />
            Transcribing…
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: '24px' }}>

        {/* Capture source. Defaults to the server so existing behaviour is
            unchanged unless you deliberately switch. */}
        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>
            Capture From
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            {[
              { key: 'server', icon: Server, title: 'This PC', sub: 'Meeting is on the MeetScribe machine' },
              { key: 'browser', icon: Laptop, title: 'This Browser', sub: 'Meeting is on the laptop you’re using' },
            ].map(({ key, icon: Icon, title, sub }) => {
              const active = mode === key
              return (
                <button
                  key={key}
                  onClick={() => !isBusy && setMode(key)}
                  disabled={isBusy}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: '10px', textAlign: 'left',
                    padding: '12px 14px', borderRadius: '10px', cursor: isBusy ? 'not-allowed' : 'pointer',
                    border: active ? '1.5px solid #4f46e5' : '1.5px solid #d1d5db',
                    background: active ? '#eef2ff' : '#fff',
                    fontFamily: 'Inter, system-ui, sans-serif', opacity: isBusy && !active ? 0.5 : 1,
                  }}
                >
                  <Icon size={16} style={{ color: active ? '#4f46e5' : '#9ca3af', marginTop: '1px', flexShrink: 0 }} />
                  <span>
                    <span style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: active ? '#3730a3' : '#374151' }}>{title}</span>
                    <span style={{ display: 'block', fontSize: '11px', color: '#9ca3af', marginTop: '2px' }}>{sub}</span>
                  </span>
                </button>
              )
            })}
          </div>
          {mode === 'browser' && !isCaptureSupported() && (
            <p style={{ fontSize: '12px', color: '#b45309', background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: '8px', padding: '8px 12px', marginTop: '10px' }}>
              {unsupportedReason()}
            </p>
          )}
        </div>

        {/* Meeting name */}
        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>
            Meeting Name
          </label>
          <input
            type="text"
            value={meetingName}
            onChange={e => setMeetingName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !isBusy && handleStart()}
            placeholder="e.g. Team Standup — April 24"
            disabled={isBusy}
            style={{
              width: '100%', padding: '10px 14px', fontSize: '14px', color: '#111827',
              border: '1.5px solid #d1d5db', borderRadius: '10px', outline: 'none',
              background: isBusy ? '#f9fafb' : '#fff', cursor: isBusy ? 'not-allowed' : 'text',
              fontFamily: 'Inter, system-ui, sans-serif', boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Browser-mode device panel — the mic list here is the laptop's own. */}
        {mode === 'browser' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>
                <Mic size={11} /> Microphone
              </label>
              <select
                value={browserMic}
                onChange={e => setBrowserMic(e.target.value)}
                disabled={isBusy}
                style={{
                  width: '100%', padding: '10px 36px 10px 14px', fontSize: '13px', color: '#374151',
                  border: '1.5px solid #d1d5db', borderRadius: '10px', outline: 'none',
                  background: isBusy ? '#f9fafb' : '#fff', appearance: 'none',
                  cursor: isBusy ? 'not-allowed' : 'pointer', boxSizing: 'border-box',
                  fontFamily: 'Inter, system-ui, sans-serif',
                  backgroundImage: chevron, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 12px center',
                }}
              >
                <option value="">Default microphone</option>
                {browserMics.map((d, i) => (
                  <option key={d.deviceId} value={d.deviceId}>{d.label || `Microphone ${i + 1}`}</option>
                ))}
              </select>
              <p style={{ fontSize: '11px', color: '#9ca3af', marginTop: '5px' }}>This laptop’s mic — your voice</p>
            </div>
            <div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>
                <Volume2 size={11} /> Meeting Audio
              </label>
              <div style={{
                width: '100%', padding: '10px 14px', fontSize: '13px', color: '#6b7280',
                border: '1.5px solid #e5e7eb', borderRadius: '10px',
                background: '#f9fafb', boxSizing: 'border-box',
                fontFamily: 'Inter, system-ui, sans-serif',
              }}>
                Shared tab (picked on start)
              </div>
              <p style={{ fontSize: '11px', color: '#9ca3af', marginTop: '5px' }}>Choose the Meet tab, tick “share tab audio”</p>
            </div>
          </div>
        )}

        {/* Device selectors */}
        {mode === 'server' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>
              <Mic size={11} /> Microphone
            </label>
            <select
              value={micDevice}
              onChange={e => setMicDevice(e.target.value)}
              disabled={isBusy}
              style={{
                width: '100%', padding: '10px 36px 10px 14px', fontSize: '13px', color: '#374151',
                border: '1.5px solid #d1d5db', borderRadius: '10px', outline: 'none',
                background: isBusy ? `#f9fafb ${chevron} no-repeat right 12px center` : `#fff ${chevron} no-repeat right 12px center`,
                appearance: 'none', cursor: isBusy ? 'not-allowed' : 'pointer',
                fontFamily: 'Inter, system-ui, sans-serif', boxSizing: 'border-box',
                backgroundImage: chevron, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 12px center',
              }}
            >
              {mics.length === 0
                ? <option value="">Loading…</option>
                : mics.map(d => <option key={d.index} value={d.index}>{d.name}</option>)
              }
            </select>
            <p style={{ fontSize: '11px', color: '#9ca3af', marginTop: '5px' }}>Your voice — headset or built-in mic</p>
          </div>
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>
              <Volume2 size={11} /> System Audio
            </label>
            <div style={{
              width: '100%', padding: '10px 14px', fontSize: '13px', color: '#6b7280',
              border: '1.5px solid #e5e7eb', borderRadius: '10px',
              background: '#f9fafb', boxSizing: 'border-box',
              fontFamily: 'Inter, system-ui, sans-serif',
            }}>
              Auto (follows active output)
            </div>
            <p style={{ fontSize: '11px', color: '#9ca3af', marginTop: '5px' }}>Captures Zoom / Teams / Meet audio</p>
          </div>
        </div>
        )}

        {/* How-to hint, shown before starting a browser capture */}
        {mode === 'browser' && !isBusy && isCaptureSupported() && (
          <div style={{ padding: '12px 16px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '10px', marginBottom: '16px' }}>
            <p style={{ fontSize: '12px', color: '#1e40af', margin: 0, fontWeight: 600, marginBottom: '4px' }}>When you press Start, Chrome will ask what to share:</p>
            <p style={{ fontSize: '12px', color: '#1e40af', margin: 0, lineHeight: 1.6 }}>
              Pick the <strong>Chrome Tab</strong> section → choose your <strong>Google Meet</strong> tab →
              make sure <strong>“Also share tab audio”</strong> is switched on → Share.
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', fontSize: '13px', color: '#dc2626', marginBottom: '16px' }}>
            {error}
          </div>
        )}

        {/* Pre-flight warning shown the moment recording starts (e.g. Bluetooth output) */}
        {isRecording && startWarning && (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px 16px', background: '#fffbeb', border: '1.5px solid #f59e0b', borderRadius: '12px', marginBottom: '12px' }}>
            <span style={{ fontSize: '16px', lineHeight: 1.3 }}>🎧</span>
            <p style={{ fontSize: '13px', color: '#92400e', margin: 0, fontWeight: 500, flex: 1 }}>{startWarning}</p>
            <button onClick={() => setStartWarning(null)} style={{ background: 'none', border: 'none', color: '#92400e', cursor: 'pointer', fontSize: '16px', lineHeight: 1, padding: 0 }}>×</button>
          </div>
        )}

        {/* Audio-health warning (dead / silent / Bluetooth system audio) */}
        {isRecording && liveData?.warning && (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px 16px', background: '#fffbeb', border: '1.5px solid #f59e0b', borderRadius: '12px', marginBottom: '12px' }}>
            <span style={{ fontSize: '16px', lineHeight: 1.3 }}>⚠️</span>
            <p style={{ fontSize: '13px', color: '#92400e', margin: 0, fontWeight: 500 }}>{liveData.warning}</p>
          </div>
        )}

        {/* Live panel — browser capture. Shows each channel separately so a
            silent meeting stream is obvious while there's still time to fix it. */}
        {isRecording && mode === 'browser' && (
          <div style={{ padding: '16px 20px', background: 'linear-gradient(135deg, #ecfdf5, #f0fdfa)', border: '1.5px solid #6ee7b7', borderRadius: '12px', marginBottom: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '20px', marginBottom: '14px' }}>
              <div style={{ textAlign: 'center', minWidth: '110px' }}>
                <p style={{ fontSize: '10px', fontWeight: 700, color: '#6ee7b7', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 4px' }}>Elapsed</p>
                <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '30px', fontWeight: 500, color: '#059669', margin: 0, letterSpacing: '-1px' }}>{formatTime(elapsed)}</p>
                <p style={{ fontFamily: 'monospace', fontSize: '11px', color: '#6ee7b7', margin: '4px 0 0' }}>
                  {(uploaded / 1024 / 1024).toFixed(1)} MB sent
                </p>
              </div>
              <div style={{ width: '1px', height: '52px', background: '#a7f3d0' }} />
              <div style={{ flex: 1 }}>
                {[
                  { label: '🎤 Your mic', value: levels.mic },
                  { label: '🔊 Meeting audio', value: levels.system },
                ].map(({ label, value }) => {
                  // Speech sits near the low end of a linear scale, so bars use a
                  // square-root curve to stay readable at normal talking volume.
                  const pct = Math.min(100, Math.sqrt(value) * 220)
                  return (
                    <div key={label} style={{ marginBottom: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#065f46', marginBottom: '3px' }}>
                        <span>{label}</span>
                        <span style={{ color: value > 0.004 ? '#059669' : '#d97706', fontWeight: 600 }}>
                          {value > 0.004 ? 'live' : 'silent'}
                        </span>
                      </div>
                      <div style={{ height: '6px', background: '#d1fae5', borderRadius: '99px', overflow: 'hidden' }}>
                        <div style={{ width: `${pct}%`, height: '100%', background: value > 0.004 ? '#10b981' : '#fbbf24', transition: 'width 120ms linear' }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
            <p style={{ fontSize: '11px', color: '#047857', margin: 0 }}>
              Streaming to MeetScribe on your PC — transcription starts when you stop.
            </p>
          </div>
        )}

        {/* Live panel */}
        {isRecording && mode === 'server' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px', padding: '16px 20px', background: 'linear-gradient(135deg, #ecfdf5, #f0fdfa)', border: '1.5px solid #6ee7b7', borderRadius: '12px', marginBottom: '20px' }}>
            <div style={{ textAlign: 'center', minWidth: '110px' }}>
              <p style={{ fontSize: '10px', fontWeight: 700, color: '#6ee7b7', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 4px' }}>Elapsed</p>
              <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '30px', fontWeight: 500, color: '#059669', margin: 0, letterSpacing: '-1px' }}>{formatTime(elapsed)}</p>
              {liveData && <p style={{ fontFamily: 'monospace', fontSize: '11px', color: '#6ee7b7', margin: '4px 0 0' }}>{liveData.duration}s captured</p>}
            </div>
            <div style={{ width: '1px', height: '52px', background: '#a7f3d0' }} />
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: '10px', fontWeight: 700, color: '#6ee7b7', textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 6px' }}>Live Status</p>
              {liveData
                ? <p style={{ fontSize: '13px', color: '#065f46' }}>
                    Recording…
                    {liveData.mic_chunks > 0 && <span style={{ marginLeft: '8px' }}>🎤 {liveData.mic_chunks} mic</span>}
                    {liveData.loopback_chunks > 0 && <span style={{ marginLeft: '8px' }}>🔊 {liveData.loopback_chunks} system</span>}
                  </p>
                : <p style={{ fontSize: '13px', color: '#059669' }}>Listening…</p>
              }
            </div>
          </div>
        )}

        {/* Button */}
        <div>
          {!isRecording ? (
            <button
              onClick={handleStart}
              disabled={isTranscribing}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '8px',
                padding: '10px 24px', background: isTranscribing ? '#a5b4fc' : '#4f46e5',
                color: '#fff', border: 'none', borderRadius: '10px', fontSize: '14px',
                fontWeight: 600, cursor: isTranscribing ? 'not-allowed' : 'pointer',
                fontFamily: 'Inter, system-ui, sans-serif',
                boxShadow: '0 2px 8px rgba(79,70,229,0.35)',
              }}
            >
              <Circle size={13} style={{ fill: '#fff' }} />
              Start Recording
            </button>
          ) : (
            <button
              onClick={handleStop}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '8px',
                padding: '10px 24px', background: '#ef4444',
                color: '#fff', border: 'none', borderRadius: '10px', fontSize: '14px',
                fontWeight: 600, cursor: 'pointer', fontFamily: 'Inter, system-ui, sans-serif',
                boxShadow: '0 2px 8px rgba(239,68,68,0.35)',
              }}
            >
              <Square size={13} style={{ fill: '#fff' }} />
              Stop Recording
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
