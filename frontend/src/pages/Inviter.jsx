import { useState, useEffect } from 'react'
import { Play, Square, Upload, Link } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function Inviter() {
  const [targetChat, setTargetChat] = useState('')
  const [inviteLimit, setInviteLimit] = useState(15)
  const [delayMin, setDelayMin] = useState(30)
  const [delayMax, setDelayMax] = useState(60)
  const [baseFile, setBaseFile] = useState(null)
  const [baseCount, setBaseCount] = useState(0)
  const [inviting, setInviting] = useState(false)
  const [taskId, setTaskId] = useState(null)
  const [invitedCount, setInvitedCount] = useState(0)
  const [errorCount, setErrorCount] = useState(0)

  const handleBaseUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setBaseFile(file)
    const text = await file.text()
    const lines = text.split('\n').filter(l => l.trim()).length
    setBaseCount(lines)
  }

  const handleStart = async () => {
    if (!targetChat.trim()) return alert('Введіть посилання на канал/групу')
    if (baseCount === 0 || !baseFile) return alert('Завантажте базу юзерів')
    setInviting(true)
    setInvitedCount(0)
    setErrorCount(0)
    try {
      // 1. Upload base file
      let targetsFile = ''
      const baseForm = new FormData()
      baseForm.append('file', baseFile)
      const baseRes = await fetch(`${API}/api/inviter/upload-base`, { method: 'POST', body: baseForm })
      if (baseRes.ok) {
        const baseData = await baseRes.json()
        targetsFile = baseData.saved_filename || ''
      } else {
        alert('Помилка завантаження бази')
        setInviting(false)
        return
      }

      // 2. Create task
      const form = new FormData()
      form.append('target_chat', targetChat)
      form.append('targets_file', targetsFile)
      form.append('invites_per_account', inviteLimit)
      form.append('delay_min', delayMin)
      form.append('delay_max', delayMax)
      const res = await fetch(`${API}/api/inviter/create-task`, { method: 'POST', body: form })
      if (res.ok) {
        const data = await res.json()
        setTaskId(data.task_id)
        await fetch(`${API}/api/inviter/${data.task_id}/start`, { method: 'POST' })
      }
    } catch { 
      alert('Бекенд не запущено або помилка')
      setInviting(false)
    }
  }

  const handleStop = async () => {
    setInviting(false)
    if (taskId) {
      try { await fetch(`${API}/api/inviter/${taskId}/stop`, { method: 'POST' }) } catch {}
    }
  }

  // Poll for status
  useEffect(() => {
    let interval;
    if (inviting && taskId) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${API}/api/inviter/tasks`)
          if (res.ok) {
            const data = await res.json()
            const task = data.tasks.find(t => t.id === taskId)
            if (task) {
              setInvitedCount(task.total_invited || 0)
              setErrorCount(task.total_failed || 0)
              if (task.status === 'done' || task.status === 'stopped') {
                setInviting(false)
              }
            }
          }
        } catch {}
      }, 3000)
    }
    return () => clearInterval(interval)
  }, [inviting, taskId])

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Inviter</h2>
          <p className="subtitle">Інвайтинг користувачів у канали та групи</p>
        </div>
        <div className="btn-group">
          {!inviting ? (
            <button className="btn btn-primary btn-sm" onClick={handleStart}>
              <Play size={14} /> Запустити інвайтинг
            </button>
          ) : (
            <button className="btn btn-danger btn-sm" onClick={handleStop}>
              <Square size={14} /> Зупинити
            </button>
          )}
        </div>
      </div>
      <div className="page-body">
        {/* Target */}
        <div className="card section">
          <div className="card-header">
            <span className="card-title"><Link size={15} /> Ціль (канал/група)</span>
          </div>
          <div className="input-group">
            <label className="input-label">Посилання на Telegram-канал або групу</label>
            <input className="input" value={targetChat} onChange={e => setTargetChat(e.target.value)} placeholder="https://t.me/your_channel" />
          </div>
        </div>

        {/* Base */}
        <div className="card section">
          <div className="card-header">
            <span className="card-title"><Upload size={15} /> База користувачів</span>
            {baseCount > 0 && <span className="badge active"><span className="badge-dot"></span> {baseCount} юзерів</span>}
          </div>
          {baseCount === 0 ? (
            <label className="dropzone" style={{ cursor: 'pointer' }}>
              <div className="dropzone-icon">👥</div>
              <div className="dropzone-text">Завантажте спарсений список користувачів</div>
              <div className="dropzone-hint">.txt файл з @username або ID</div>
              <input type="file" accept=".txt,.csv" style={{ display: 'none' }} onChange={handleBaseUpload} />
            </label>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                📄 <strong style={{ color: 'var(--text-primary)' }}>{baseFile?.name}</strong> — {baseCount} записів
              </span>
              <button className="btn btn-danger btn-sm" onClick={() => { setBaseFile(null); setBaseCount(0) }}>Скинути</button>
            </div>
          )}
        </div>

        {/* Settings */}
        <div className="card section">
          <div className="card-header"><span className="card-title">⚙️ Налаштування</span></div>
          <div className="form-grid cols-3">
            <div className="input-group">
              <label className="input-label">Інвайтів з 1 акаунта (макс 20)</label>
              <div className="range-group">
                <input type="range" min="5" max="20" value={inviteLimit} onChange={e => setInviteLimit(+e.target.value)} />
                <span className="range-value">{inviteLimit}</span>
              </div>
            </div>
            <div className="input-group">
              <label className="input-label">Мін. затримка (сек)</label>
              <div className="range-group">
                <input type="range" min="15" max="120" value={delayMin} onChange={e => setDelayMin(+e.target.value)} />
                <span className="range-value">{delayMin}с</span>
              </div>
            </div>
            <div className="input-group">
              <label className="input-label">Макс. затримка (сек)</label>
              <div className="range-group">
                <input type="range" min="30" max="180" value={delayMax} onChange={e => setDelayMax(+e.target.value)} />
                <span className="range-value">{delayMax}с</span>
              </div>
            </div>
          </div>
        </div>

        {/* Status */}
        {inviting && (
          <div className="card" style={{ borderColor: 'rgba(0,170,255,0.3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span className="badge running"><span className="badge-dot"></span> Інвайтинг активний</span>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                Запрошено: <strong style={{ color: 'var(--neon-green)' }}>{invitedCount}</strong> / {baseCount} |
                Помилок: <strong style={{ color: 'var(--neon-red)' }}>{errorCount}</strong>
              </span>
            </div>
          </div>
        )}

        {/* Info card */}
        <div className="card" style={{ marginTop: '16px', borderLeft: '3px solid var(--neon-yellow)' }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--neon-yellow)' }}>⚠️ Anti-Ban порада:</strong> Рекомендовано не більше 15-20 інвайтів з одного акаунта на день.
            Програма автоматично ротує акаунти та імітує затримки для зниження ризику бану.
          </div>
        </div>
      </div>
    </>
  )
}
