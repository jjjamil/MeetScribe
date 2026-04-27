import { useEffect, useState } from 'react'
import { X, Copy, Check } from 'lucide-react'

export default function TranscriptModal({ title, content, onClose }) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const handler = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      onClick={e => e.target === e.currentTarget && onClose()}
      style={{ position: 'fixed', inset: 0, zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px', background: 'rgba(17,24,39,0.5)', backdropFilter: 'blur(4px)' }}
    >
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: '20px', width: '100%', maxWidth: '680px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #f3f4f6' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#111827', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: '16px' }}>{title}</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            <button
              onClick={handleCopy}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', padding: '6px 12px', background: '#f3f4f6', border: 'none', borderRadius: '8px', fontSize: '12px', fontWeight: 600, color: '#374151', cursor: 'pointer', fontFamily: 'Inter, system-ui, sans-serif' }}
            >
              {copied ? <><Check size={11} color="#10b981" /> Copied</> : <><Copy size={11} /> Copy</>}
            </button>
            <button
              onClick={onClose}
              style={{ display: 'inline-flex', padding: '6px', background: '#f3f4f6', border: 'none', borderRadius: '8px', cursor: 'pointer', color: '#6b7280' }}
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          <pre style={{ margin: 0, padding: '16px', background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: '10px', fontSize: '12px', lineHeight: 1.75, color: '#374151', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'JetBrains Mono, Consolas, monospace', overflowY: 'auto', maxHeight: '55vh' }}>
            {content || '(empty)'}
          </pre>
        </div>
      </div>
    </div>
  )
}
