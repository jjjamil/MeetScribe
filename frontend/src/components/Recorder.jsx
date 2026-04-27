import { useState, useEffect, useRef } from 'react'
import { Mic, Volume2, Square, Circle, Loader2 } from 'lucide-react'

export default function Recorder({ status, devices, onStart, onStop }) {
  const [meetingName, setMeetingName] = useState('')
  const [micDevice, setMicDevice] = useState('')
  const [loopbackDevice, setLoopbackDevice] = useState('')
  const [error, setError] = useState('')
  const [liveData, setLiveData] = useState(null)
  const [elapsed, setElapsed] = useState(0)

  const liveRef = useRef(null)
  const timerRef = useRef(null)
  const startTimeRef = useRef(null)

  const isRecording = status === 'recording'
  const isTranscribing = status === 'transcribing'
  const isBusy = isRecording || isTranscribing

  useEffect(() => {
    if (!devices.length) return
    const mics = devices.filter(d => !d.is_loopback)
    const loopbacks = devices.filter(d => d.is_loopback)
    if (mics.length && !micDevice) setMicDevice(String(mics[0].index))
    if (loopbacks.length && !loopbackDevice) setLoopbackDevice(String(loopbacks[0].index))
  }, [devices])

  useEffect(() => {
    if (isRecording) {
      startTimeRef.current = Date.now()
      setElapsed(0)
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000))
      }, 1000)
      liveRef.current = setInterval(async () => {
        try {
          const d = await fetch('/api/live_status').then(r => r.json())
          setLiveData(d)
        } catch {}
      }, 1000)
    } else {
      clearInterval(timerRef.current)
      clearInterval(liveRef.current)
      setLiveData(null)
      setElapsed(0)
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
    try {
      await onStart({
        meetingName: meetingName.trim(),
        micDevice: micDevice !== '' ? parseInt(micDevice) : null,
        loopbackDevice: loopbackDevice !== '' ? parseInt(loopbackDevice) : null,
      })
    } catch (e) { setError(e.message) }
  }

  const handleStop = async () => {
    setError('')
    try { await onStop(); setMeetingName('') }
    catch (e) { setError(e.message) }
  }

  const mics = devices.filter(d => !d.is_loopback)
  const loopbacks = devices.filter(d => d.is_loopback)

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

        {/* Device selectors */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
          {[
            { label: 'Microphone', icon: <Mic size={11} />, value: micDevice, onChange: setMicDevice, options: mics, defaultOpt: null, hint: 'Your voice — headset or built-in mic' },
            { label: 'System Audio', icon: <Volume2 size={11} />, value: loopbackDevice, onChange: setLoopbackDevice, options: loopbacks, defaultOpt: '— None (mic only) —', hint: 'Captures Zoom / Teams / Meet audio' },
          ].map(({ label, icon, value, onChange, options, defaultOpt, hint }) => (
            <div key={label}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>
                {icon} {label}
              </label>
              <select
                value={value}
                onChange={e => onChange(e.target.value)}
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
                {defaultOpt && <option value="">{defaultOpt}</option>}
                {options.length === 0
                  ? <option value="">Loading…</option>
                  : options.map(d => <option key={d.index} value={d.index}>{d.name}</option>)
                }
              </select>
              <p style={{ fontSize: '11px', color: '#9ca3af', marginTop: '5px' }}>{hint}</p>
            </div>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div style={{ padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', fontSize: '13px', color: '#dc2626', marginBottom: '16px' }}>
            {error}
          </div>
        )}

        {/* Live panel */}
        {isRecording && (
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
