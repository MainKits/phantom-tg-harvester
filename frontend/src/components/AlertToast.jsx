import React, { useState, useEffect } from 'react'
import { API } from '../apiConfig'

export default function AlertToast() {
  const [toasts, setToasts] = useState([])

  const dismissToast = async (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    try {
      const fd = new FormData()
      fd.append('alert_id', id)
      await fetch(`${API}/api/system/alerts/ack`, {
        method: 'POST',
        body: fd
      })
    } catch {
      // ignore ack errors
    }
  }

  useEffect(() => {
    let isMounted = true

    const pollAlerts = async () => {
      try {
        const res = await fetch(`${API}/api/system/alerts`)
        if (res.ok) {
          const data = await res.json()
          if (data.alerts && data.alerts.length > 0 && isMounted) {
            setToasts((prev) => {
              const prevIds = new Set(prev.map((t) => t.id))
              const newAlerts = data.alerts.filter((a) => !prevIds.has(a.id))
              if (newAlerts.length === 0) return prev
              return [...prev, ...newAlerts]
            })
          }
        }
      } catch {
        // quiet error on network drop
      }
    }

    pollAlerts()
    const timer = setInterval(pollAlerts, 3000)
    return () => {
      isMounted = false
      clearInterval(timer)
    }
  }, [])

  // Auto-dismiss after 12 seconds
  useEffect(() => {
    if (toasts.length === 0) return
    const timers = toasts.map((t) =>
      setTimeout(() => {
        dismissToast(t.id)
      }, 12000)
    )
    return () => timers.forEach(clearTimeout)
  }, [toasts])

  if (toasts.length === 0) return null

  return (
    <div
      style={{
        position: 'fixed',
        top: 20,
        right: 20,
        zIndex: 99999,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        maxWidth: 380,
        width: '100%',
        pointerEvents: 'none'
      }}
    >
      {toasts.map((toast) => {
        const isBan = toast.type === 'banned'
        const borderColor = isBan ? '#ef4444' : '#f59e0b'
        const bgColor = isBan ? 'rgba(28, 10, 14, 0.96)' : 'rgba(30, 20, 10, 0.96)'
        const icon = isBan ? '🚫' : '⚠️'
        const title = isBan ? 'Акаунт заблоковано!' : 'Спам-блок на акаунті!'

        return (
          <div
            key={toast.id}
            style={{
              pointerEvents: 'auto',
              background: bgColor,
              border: `1px solid ${borderColor}`,
              boxShadow: `0 8px 24px rgba(0, 0, 0, 0.6), 0 0 16px ${borderColor}33`,
              borderRadius: 12,
              padding: '12px 16px',
              color: '#fff',
              fontFamily: 'Inter, system-ui, sans-serif',
              backdropFilter: 'blur(10px)',
              animation: 'fadeInSlide 0.3s ease-out forwards',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12
            }}
          >
            <div style={{ fontSize: 24, lineHeight: 1, marginTop: 2 }}>{icon}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: borderColor }}>
                  {title}
                </span>
                {toast.phone && (
                  <span
                    style={{
                      background: 'rgba(255, 255, 255, 0.1)',
                      padding: '2px 6px',
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 600,
                      color: '#ddd'
                    }}
                  >
                    {toast.phone}
                  </span>
                )}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: '#e2e8f0',
                  marginTop: 4,
                  lineHeight: 1.4,
                  wordBreak: 'break-word'
                }}
              >
                {toast.message}
              </div>
              {toast.details && (
                <div
                  style={{
                    fontSize: 11,
                    color: '#94a3b8',
                    marginTop: 4,
                    lineHeight: 1.3,
                    fontFamily: 'monospace'
                  }}
                >
                  {toast.details.slice(0, 120)}
                </div>
              )}
            </div>
            <button
              onClick={() => dismissToast(toast.id)}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#94a3b8',
                cursor: 'pointer',
                fontSize: 16,
                lineHeight: 1,
                padding: '2px 4px',
                borderRadius: 4
              }}
              title="Закрити"
            >
              ✕
            </button>
          </div>
        )
      })}
    </div>
  )
}
