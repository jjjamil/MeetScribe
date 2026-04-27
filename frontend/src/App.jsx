import { useState, useEffect, useRef, useCallback } from 'react'
import Topbar from './components/Topbar'
import Recorder from './components/Recorder'
import RecordingsList from './components/RecordingsList'
import TranscriptModal from './components/TranscriptModal'

export default function App() {
  const [status, setStatus] = useState('idle') // idle | recording | transcribing
  const [devices, setDevices] = useState([])
  const [recordings, setRecordings] = useState([])
  const [modal, setModal] = useState(null) // { title, content }

  const pollRef = useRef(null)

  useEffect(() => {
    fetchDevices()
    fetchRecordings()
    fetch('/api/status')
      .then(r => r.json())
      .then(d => {
        setStatus(d.status)
        if (d.status === 'transcribing') startStatusPoll()
      })
      .catch(() => {})
  }, [])

  const fetchDevices = async () => {
    try {
      const res = await fetch('/api/devices')
      const data = await res.json()
      if (data.success) setDevices(data.devices)
    } catch {}
  }

  const fetchRecordings = useCallback(async () => {
    try {
      const res = await fetch('/api/recordings')
      setRecordings(await res.json())
    } catch {}
  }, [])

  const startStatusPoll = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const d = await fetch('/api/status').then(r => r.json())
        setStatus(prev => (prev === 'recording' ? prev : d.status))
        if (d.status === 'idle') {
          clearInterval(pollRef.current)
          pollRef.current = null
          fetchRecordings()
        }
      } catch {}
    }, 2000)
  }, [fetchRecordings])

  const handleStart = async ({ meetingName, micDevice, loopbackDevice }) => {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        meeting_name: meetingName,
        mic_device: micDevice,
        loopback_device: loopbackDevice,
      }),
    })
    const data = await res.json()
    if (!data.success) throw new Error(data.error)
    setStatus('recording')
  }

  const handleStop = async () => {
    const res = await fetch('/api/stop', { method: 'POST' })
    const data = await res.json()
    if (!data.success) throw new Error(data.error)
    setStatus('transcribing')
    fetchRecordings()
    startStatusPoll()
  }

  const handleDelete = async (id) => {
    const res = await fetch('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    })
    const data = await res.json()
    if (data.success) fetchRecordings()
  }

  const handleView = async (id, type) => {
    const endpoint = type === 'summary' ? `/api/summary/${id}` : `/api/transcript/${id}`
    const res = await fetch(endpoint)
    const data = await res.json()
    if (!data.success) return alert(`${type === 'summary' ? 'Summary' : 'Transcript'} not ready yet.`)
    const rec = recordings.find(r => r.id === id)
    const label = type === 'summary' ? 'Summary' : 'Transcript'
    setModal({ title: rec ? `${label} — ${rec.name}` : label, content: data.content })
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f3f4f6' }}>
      <Topbar status={status} />
      <main style={{ maxWidth: '896px', margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <Recorder
          status={status}
          devices={devices}
          onStart={handleStart}
          onStop={handleStop}
        />
        <RecordingsList
          recordings={recordings}
          onView={handleView}
          onDelete={handleDelete}
        />
      </main>
      {modal && (
        <TranscriptModal
          title={modal.title}
          content={modal.content}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
