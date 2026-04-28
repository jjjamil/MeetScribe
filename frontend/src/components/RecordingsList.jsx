import { Trash2, FileText, Sparkles, Clock, Calendar, Download } from 'lucide-react'

function StatusBadge({ status }) {
  const map = {
    recorded:    { label: 'Processing', bg: '#fef3c7', color: '#92400e', dot: '#f59e0b' },
    transcribed: { label: 'Ready',      bg: '#d1fae5', color: '#065f46', dot: '#10b981' },
    error:       { label: 'Error',      bg: '#fee2e2', color: '#991b1b', dot: '#ef4444' },
  }
  const cfg = map[status] ?? map.recorded
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '3px 10px', borderRadius: '99px', fontSize: '11px', fontWeight: 700, background: cfg.bg, color: cfg.color }}>
      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: cfg.dot, flexShrink: 0 }} />
      {cfg.label}
    </span>
  )
}

function formatDuration(seconds) {
  if (!seconds) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

export default function RecordingsList({ recordings, onView, onDelete }) {
  const handleDelete = (id) => {
    if (confirm('Delete this recording and all its files?')) onDelete(id)
  }

  const handleDownload = async (id, name) => {
    const res = await fetch(`/api/transcript/${id}`)
    const data = await res.json()
    if (!data.success) return alert('Transcript not ready yet.')
    const blob = new Blob([data.content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${name.replace(/[^a-z0-9]/gi, '_')}_transcript.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      {/* Section header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <p style={{ fontSize: '11px', fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>Recordings</p>
        {recordings.length > 0 && (
          <span style={{ fontSize: '11px', fontWeight: 700, color: '#4f46e5', background: '#eef2ff', borderRadius: '99px', padding: '2px 10px' }}>
            {recordings.length}
          </span>
        )}
      </div>

      {recordings.length === 0 ? (
        <div style={{ background: '#fff', border: '1.5px dashed #d1d5db', borderRadius: '16px', padding: '56px 32px', textAlign: 'center' }}>
          <div style={{ fontSize: '36px', marginBottom: '12px', opacity: 0.3 }}>🎙️</div>
          <p style={{ fontWeight: 600, fontSize: '14px', color: '#6b7280', margin: '0 0 4px' }}>No recordings yet</p>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>Start your first meeting above</p>
        </div>
      ) : (
        <div style={{ background: '#fff', border: '1px solid #d1d5db', borderRadius: '16px', boxShadow: '0 4px 16px rgba(0,0,0,0.08)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                {['#', 'Title', 'Date', 'Duration', 'Status', 'Actions'].map((h, i) => (
                  <th key={h} style={{
                    padding: '10px 16px', textAlign: i === 5 ? 'right' : 'left',
                    fontSize: '10.5px', fontWeight: 700, color: '#9ca3af',
                    textTransform: 'uppercase', letterSpacing: '0.06em',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recordings.map((rec, idx) => (
                <tr key={rec.id} style={{ borderBottom: '1px solid #f3f4f6' }}
                  onMouseEnter={e => e.currentTarget.style.background = '#f9fafb'}
                  onMouseLeave={e => e.currentTarget.style.background = '#fff'}
                >
                  <td style={{ padding: '13px 16px' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: '11px', color: '#d1d5db', fontWeight: 600 }}>{idx + 1}</span>
                  </td>
                  <td style={{ padding: '13px 16px' }}>
                    <span style={{ fontWeight: 600, color: '#111827' }}>{rec.name}</span>
                  </td>
                  <td style={{ padding: '13px 16px' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '5px', color: '#6b7280', fontSize: '12px' }}>
                      <Calendar size={11} />{rec.date}
                    </span>
                  </td>
                  <td style={{ padding: '13px 16px' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '5px', color: '#6b7280', fontSize: '12px', fontFamily: 'monospace' }}>
                      <Clock size={11} />{formatDuration(rec.duration)}
                    </span>
                  </td>
                  <td style={{ padding: '13px 16px' }}>
                    <StatusBadge status={rec.status} />
                  </td>
                  <td style={{ padding: '13px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px' }}>
                      {(rec.transcript_file || rec.transcript_path) ? (
                        <>
                          <button onClick={() => onView(rec.id, 'transcript')} style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '5px 10px', background: '#ecfdf5', color: '#059669', border: '1px solid #a7f3d0', borderRadius: '7px', fontSize: '12px', fontWeight: 600, cursor: 'pointer', fontFamily: 'Inter, system-ui, sans-serif' }}>
                            <FileText size={11} /> Transcript
                          </button>
                          <button onClick={() => handleDownload(rec.id, rec.name)} title="Download transcript as .txt" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '5px 10px', background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0', borderRadius: '7px', fontSize: '12px', fontWeight: 600, cursor: 'pointer', fontFamily: 'Inter, system-ui, sans-serif' }}>
                            <Download size={11} /> Download
                          </button>
                          <button onClick={() => onView(rec.id, 'summary')} style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '5px 10px', background: '#eef2ff', color: '#4f46e5', border: '1px solid #c7d2fe', borderRadius: '7px', fontSize: '12px', fontWeight: 600, cursor: 'pointer', fontFamily: 'Inter, system-ui, sans-serif' }}>
                            <Sparkles size={11} /> Summary
                          </button>
                        </>
                      ) : (
                        <span style={{ fontSize: '12px', color: '#9ca3af', fontStyle: 'italic' }}>
                          {rec.status === 'error' ? '❌ Error' : '⏳ Processing…'}
                        </span>
                      )}
                      <button onClick={() => handleDelete(rec.id)} title="Delete" style={{ display: 'inline-flex', padding: '5px', background: 'transparent', border: 'none', borderRadius: '6px', cursor: 'pointer', color: '#d1d5db' }}
                        onMouseEnter={e => { e.currentTarget.style.background = '#fef2f2'; e.currentTarget.style.color = '#ef4444' }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#d1d5db' }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
