import { useState } from 'react'
import { Key, Shield, Lock, CheckCircle2, AlertCircle, ExternalLink } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function LicenseScreen({ onActivated }) {
  const [key, setKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const handleActivate = async () => {
    const trimmed = key.trim().toUpperCase()
    if (!trimmed) return
    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const fd = new FormData()
      fd.append('key', trimmed)
      const res = await fetch(`${API}/api/license/activate`, { method: 'POST', body: fd })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Помилка активації')
      setSuccess(`Ліцензія активована до: ${new Date(data.expires_at).toLocaleDateString('uk-UA')}`)
      setTimeout(() => onActivated(), 1500)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #0a0a0f 0%, #12121e 50%, #0a0a0f 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: "'Inter', sans-serif",
      position: 'fixed',
      inset: 0,
      zIndex: 9999,
    }}>
      {/* Glowing background blobs */}
      <div style={{ position: 'absolute', top: '15%', left: '10%', width: '400px', height: '400px', background: 'radial-gradient(circle, rgba(132,0,255,0.15) 0%, transparent 70%)', borderRadius: '50%', filter: 'blur(40px)', pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', bottom: '10%', right: '10%', width: '350px', height: '350px', background: 'radial-gradient(circle, rgba(0,200,255,0.1) 0%, transparent 70%)', borderRadius: '50%', filter: 'blur(40px)', pointerEvents: 'none' }} />

      <div style={{
        background: 'rgba(255,255,255,0.03)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.08)',
        borderRadius: '24px',
        padding: '50px 50px',
        width: '100%',
        maxWidth: '480px',
        boxShadow: '0 40px 80px rgba(0,0,0,0.5)',
        position: 'relative',
        overflow: 'hidden',
      }}>
        {/* Top accent line */}
        <div style={{ position: 'absolute', top: 0, left: '10%', right: '10%', height: '2px', background: 'linear-gradient(90deg, transparent, #8400ff, #00c8ff, transparent)' }} />

        {/* Logo / Icon */}
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div style={{
            width: '72px', height: '72px',
            background: 'linear-gradient(135deg, #8400ff, #5500aa)',
            borderRadius: '20px',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '36px',
            boxShadow: '0 0 30px rgba(132,0,255,0.4)',
            marginBottom: '16px',
          }}>👻</div>
          <h1 style={{ margin: 0, fontSize: '26px', fontWeight: 800, color: '#fff', letterSpacing: '-0.5px' }}>
            Phantom TG Harvester
          </h1>
          <p style={{ margin: '8px 0 0', color: '#666', fontSize: '14px' }}>
            Введіть ліцензійний ключ для активації
          </p>
        </div>

        {/* Features row */}
        <div style={{ display: 'flex', gap: '12px', marginBottom: '32px', justifyContent: 'center' }}>
          {[
            { icon: <Shield size={14} />, text: 'Захищено' },
            { icon: <Lock size={14} />, text: 'Ліцензія' },
            { icon: <Key size={14} />, text: 'Активація' },
          ].map((f, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '20px', padding: '5px 12px',
              fontSize: '12px', color: '#888',
            }}>
              {f.icon} {f.text}
            </div>
          ))}
        </div>

        {/* Key input */}
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '13px', color: '#aaa', marginBottom: '8px', fontWeight: 500 }}>
            Ліцензійний ключ
          </label>
          <input
            type="text"
            value={key}
            onChange={e => setKey(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleActivate()}
            placeholder="XXXX-XXXX-XXXX-XXXX"
            style={{
              width: '100%',
              background: 'rgba(255,255,255,0.05)',
              border: `1px solid ${error ? '#ff4757' : 'rgba(255,255,255,0.12)'}`,
              borderRadius: '12px',
              padding: '14px 18px',
              fontSize: '18px',
              letterSpacing: '3px',
              color: '#fff',
              outline: 'none',
              textAlign: 'center',
              fontFamily: 'monospace',
              fontWeight: 700,
              boxSizing: 'border-box',
              transition: 'border-color 0.2s',
            }}
          />
        </div>

        {/* Error / Success messages */}
        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            background: 'rgba(255,71,87,0.1)', border: '1px solid rgba(255,71,87,0.3)',
            borderRadius: '10px', padding: '12px 16px',
            color: '#ff6b7a', fontSize: '14px', marginBottom: '16px',
          }}>
            <AlertCircle size={18} />{error}
          </div>
        )}
        {success && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            background: 'rgba(46,213,115,0.1)', border: '1px solid rgba(46,213,115,0.3)',
            borderRadius: '10px', padding: '12px 16px',
            color: '#2ed573', fontSize: '14px', marginBottom: '16px',
          }}>
            <CheckCircle2 size={18} />{success}
          </div>
        )}

        {/* Activate button */}
        <button
          onClick={handleActivate}
          disabled={loading || !key}
          style={{
            width: '100%',
            padding: '15px',
            background: loading || !key
              ? 'rgba(255,255,255,0.05)'
              : 'linear-gradient(135deg, #8400ff, #5500aa)',
            border: 'none',
            borderRadius: '12px',
            color: loading || !key ? '#555' : '#fff',
            fontSize: '15px',
            fontWeight: 700,
            cursor: loading || !key ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s',
            boxShadow: loading || !key ? 'none' : '0 8px 24px rgba(132,0,255,0.35)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px',
          }}
        >
          {loading ? '⏳ Перевірка...' : <><Key size={18} /> Активувати</>}
        </button>

        {/* Buy link */}
        <div style={{ textAlign: 'center', marginTop: '24px' }}>
          <p style={{ color: '#555', fontSize: '13px', margin: 0 }}>
            Немає ключа?{' '}
            <a
              href="https://t.me/phantom_keys"
              target="_blank"
              rel="noreferrer"
              style={{ color: '#8400ff', textDecoration: 'none', fontWeight: 600 }}
            >
              Купити ліцензію <ExternalLink size={12} style={{ verticalAlign: 'middle' }} />
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}
