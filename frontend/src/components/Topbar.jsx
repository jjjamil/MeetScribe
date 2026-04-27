import { Mic } from 'lucide-react'

const statusConfig = {
  idle:         { label: 'Idle',         bg: '#f3f4f6', color: '#6b7280', dot: '#9ca3af' },
  recording:    { label: 'Recording',    bg: '#d1fae5', color: '#065f46', dot: '#10b981' },
  transcribing: { label: 'Transcribing', bg: '#fef3c7', color: '#92400e', dot: '#f59e0b' },
}

export default function Topbar({ status }) {
  const cfg = statusConfig[status] ?? statusConfig.idle

  return (
    <header style={{ background: '#fff', borderBottom: '1px solid #e5e7eb', position: 'sticky', top: 0, zIndex: 50, boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}>
      <div style={{ maxWidth: '896px', margin: '0 auto', padding: '0 24px', height: '56px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '32px', height: '32px', background: '#4f46e5', borderRadius: '9px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Mic size={15} color="#fff" />
          </div>
          <span style={{ fontWeight: 700, fontSize: '15px', color: '#111827', letterSpacing: '-0.2px' }}>MeetScribe</span>
          <span style={{ fontSize: '11px', color: '#d1d5db', marginLeft: '2px' }}>Windows</span>
        </div>

        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '5px 14px', borderRadius: '99px', background: cfg.bg, fontSize: '12px', fontWeight: 600, color: cfg.color }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: cfg.dot, flexShrink: 0, animation: status !== 'idle' ? 'pulse 1.2s infinite' : 'none' }} />
          {cfg.label}
        </div>
      </div>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
    </header>
  )
}
