import { useState, useEffect } from 'react'
import { Upload, Image, Play, Square, Eye, MessageSquare, Trash2 } from 'lucide-react'
import { API } from '../apiConfig'

export default function Sender() {
  const [message, setMessage] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('phantom_sender_msg') || '' : ''))
  const [targetsText, setTargetsText] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('phantom_sender_targets') || '' : ''))
  const [limit, setLimit] = useState(() => (typeof window !== 'undefined' ? parseInt(localStorage.getItem('phantom_sender_limit')) || 35 : 35))
  const [delayMin, setDelayMin] = useState(() => (typeof window !== 'undefined' ? parseInt(localStorage.getItem('phantom_sender_delay_min')) || 45 : 45))
  const [delayMax, setDelayMax] = useState(() => (typeof window !== 'undefined' ? parseInt(localStorage.getItem('phantom_sender_delay_max')) || 120 : 120))
  const [autoResponder, setAutoResponder] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('phantom_sender_ar') === 'true' : false))
  const [keywords, setKeywords] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('phantom_sender_kw') || 'так, цікаво, да, yes, +' : 'так, цікаво, да, yes, +'))
  const [forwardTo, setForwardTo] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('phantom_sender_forward') || '' : ''))
  const [sending, setSending] = useState(false)
  const [preview, setPreview] = useState('')
  const [mediaFile, setMediaFile] = useState(null)
  const [taskId, setTaskId] = useState(null)
  const [sentCount, setSentCount] = useState(0)
  const [errorCount, setErrorCount] = useState(0)

  const [sendType, setSendType] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('phantom_sender_type') || 'users' : 'users'))
  const [repeatInterval, setRepeatInterval] = useState(() => (typeof window !== 'undefined' ? parseInt(localStorage.getItem('phantom_sender_interval')) || 15 : 15))

  const baseCount = targetsText.split('\n').filter(l => l.trim()).length

  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('phantom_sender_msg', message)
      localStorage.setItem('phantom_sender_targets', targetsText)
      localStorage.setItem('phantom_sender_type', sendType)
      localStorage.setItem('phantom_sender_limit', limit)
      localStorage.setItem('phantom_sender_delay_min', delayMin)
      localStorage.setItem('phantom_sender_delay_max', delayMax)
      localStorage.setItem('phantom_sender_interval', repeatInterval)
      localStorage.setItem('phantom_sender_ar', autoResponder)
      localStorage.setItem('phantom_sender_kw', keywords)
      localStorage.setItem('phantom_sender_forward', forwardTo)
    }
  }, [message, targetsText, sendType, limit, delayMin, delayMax, repeatInterval, autoResponder, keywords, forwardTo])

  const generatePreview = () => {
    if (!message.trim()) return
    const result = message.replace(/\{([^{}]*)\}/g, (_, opts) => {
      const arr = opts.split('|')
      return arr[Math.floor(Math.random() * arr.length)]
    })
    setPreview(result)
  }

  const handleBaseUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target.result || ''
      const lines = content
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n')
        .split('\n')
        .map(l => l.trim())
        .filter(l => l && !l.startsWith('#'))
      
      const existing = targetsText.split('\n').map(l => l.trim()).filter(Boolean)
      const combined = Array.from(new Set([...existing, ...lines])).join('\n')
      setTargetsText(combined)
      if (typeof window !== 'undefined') {
        localStorage.setItem('phantom_sender_targets', combined)
      }
      alert(`✅ Імпортовано ${lines.length} рядків із файлу ${file.name}`)
    }
    reader.readAsText(file, 'UTF-8')
    e.target.value = ''
  }

  const handleMediaUpload = (e) => {
    const file = e.target.files[0]
    if (file) setMediaFile(file)
  }

  const handleStart = async () => {
    if (!message.trim()) return alert('Введіть текст повідомлення')
    const cleanTargets = targetsText.trim()
    if (!cleanTargets) {
      return alert(sendType === 'users' ? 'Введіть або завантажте базу юзерів' : 'Введіть або завантажте список чатів/каналів')
    }
    setSending(true)
    setSentCount(0)
    setErrorCount(0)
    try {
      const form = new FormData()
      form.append('message_text', message)
      form.append('targets_text', cleanTargets)
      form.append('send_type', sendType)
      form.append('repeat_interval', repeatInterval)
      form.append('spintax_enabled', 'true')
      form.append('messages_per_account', limit)
      form.append('delay_min', delayMin)
      form.append('delay_max', delayMax)
      form.append('auto_responder_enabled', autoResponder)
      form.append('auto_responder_keywords', JSON.stringify((keywords || '').split(',').map(k => k.trim())))
      form.append('forward_to_account', forwardTo || '')
      
      const res = await fetch(`${API}/api/sender/create-task`, { method: 'POST', body: form })
      if (res.ok) {
        const data = await res.json()
        setTaskId(data.task_id)
        await fetch(`${API}/api/sender/${data.task_id}/start`, { method: 'POST' })
        alert('🚀 Розсилка успішно запущена!')
      } else {
        const errJson = await res.json().catch(() => ({}))
        alert(errJson.detail || 'Помилка створення завдання')
        setSending(false)
        return
      }
    } catch (err) { 
      alert(err.message === 'Failed to fetch' 
        ? 'Сервер на Render прокидається після сну (займає ~30-50 сек). Зачекайте півхвилини та спробуйте ще раз.'
        : `Помилка: ${err.message || 'Не вдалося запустити розсилку'}`)
      setSending(false)
    }
  }

  const handleStop = async () => {
    setSending(false)
    if (taskId) {
      try { await fetch(`${API}/api/sender/${taskId}/stop`, { method: 'POST' }) } catch {}
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Sender</h2>
          <p className="subtitle">
            Масова розсилка {sendType === 'comments' ? 'по коментарях під постами каналів' : sendType === 'chats' ? 'по чатах та групах' : 'по приватних повідомленнях (ЛС)'}
          </p>
        </div>
        <div className="btn-group">
          {!sending ? (
            <button className="btn btn-primary btn-sm" onClick={handleStart}>
              <Play size={14} /> Запустити розсилку
            </button>
          ) : (
            <button className="btn btn-danger btn-sm" onClick={handleStop}>
              <Square size={14} /> Зупинити
            </button>
          )}
        </div>
      </div>
      <div className="page-body">
        
        {/* Send Type Tabs */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <button 
            className={`btn btn-sm ${sendType === 'users' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSendType('users')} style={{ flex: 1, minWidth: '130px' }}>
            👤 По юзерах (ЛС)
          </button>
          <button 
            className={`btn btn-sm ${sendType === 'chats' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSendType('chats')} style={{ flex: 1, minWidth: '130px' }}>
            📢 По чатах / групах
          </button>
          <button 
            className={`btn btn-sm ${sendType === 'comments' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSendType('comments')} style={{ flex: 1, minWidth: '130px' }}>
            💬 По коментарях каналів
          </button>
          <button 
            className={`btn btn-sm ${sendType === 'combo' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSendType('combo')} style={{ flex: 1, minWidth: '160px', border: '1px solid var(--accent)' }}>
            🚀 Комбо (Чати + Коментарі)
          </button>
        </div>

        {/* Base targets editor and upload */}
        <div className="card section">
          <div className="card-header">
            <span className="card-title">
              <Upload size={15} /> База для розсилки: {
                sendType === 'combo' 
                  ? 'чати та канали' 
                  : sendType === 'comments' 
                    ? 'канали/пости' 
                    : sendType === 'chats' 
                      ? 'чати' 
                      : 'юзери (ЛС)'
              }
            </span>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {baseCount > 0 && <span className="badge active"><span className="badge-dot"></span> {baseCount} записів</span>}
              <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
                <Upload size={13} /> Імпорт .txt
                <input type="file" accept=".txt,.csv" style={{ display: 'none' }} onChange={handleBaseUpload} />
              </label>
              {baseCount > 0 && (
                <button className="btn btn-danger btn-sm" onClick={() => setTargetsText('')}>
                  <Trash2 size={13} /> Очистити
                </button>
              )}
            </div>
          </div>
          <div className="input-group">
            <label className="input-label">
              Введіть {
                sendType === 'users' ? 'юзернейми (@username або ID)' :
                sendType === 'chats' ? 'посилання на чати/групи (@chat або https://t.me/chat)' :
                sendType === 'comments' ? 'посилання на канали (@channel або https://t.me/channel/123)' :
                'список чатів та каналів (@channel, @chat або посилання)'
              } — по одному на рядок або імпортуйте з файлу:
            </label>
            <textarea
              className="textarea"
              rows={4}
              placeholder={
                sendType === 'users' ? "@username1\n@username2\nhttps://t.me/user3" :
                sendType === 'chats' ? "@group1\nhttps://t.me/group2\nhttps://t.me/+joinhash" :
                sendType === 'comments' ? "@channel1\nhttps://t.me/channel/100" :
                "@group1\n@channel1\nhttps://t.me/chat2"
              }
              value={targetsText}
              onChange={e => setTargetsText(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: '13px' }}
            />
          </div>
        </div>

        {/* Message editor */}
        <div className="card section">
          <div className="card-header">
            <span className="card-title"><MessageSquare size={15} /> Редактор повідомлень (Spintax)</span>
            <button className="btn btn-secondary btn-sm" onClick={generatePreview} disabled={!message.trim()}><Eye size={13} /> Превʼю</button>
          </div>
          <div className="input-group">
            <label className="input-label">Текст повідомлення — використовуйте {'{варіант1|варіант2}'} для рандомізації</label>
            <textarea
              className="textarea"
              rows={5}
              value={message}
              onChange={e => setMessage(e.target.value)}
              placeholder={"{Привіт|Вітаю|Хей}! Шукаю траферів на {CPA|ПП|партнерку}. {Цікаво?|Є пропозиція}"}
            />
          </div>
          {preview && (
            <div style={{ padding: '12px 16px', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', fontSize: '13px', color: 'var(--neon-green)' }}>
              <strong style={{ color: 'var(--text-muted)', fontSize: '11px' }}>PREVIEW:</strong><br />{preview}
            </div>
          )}
          <div style={{ marginTop: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
            <label className="btn btn-secondary btn-sm" style={{ cursor: 'pointer' }}>
              <Image size={13} /> Додати медіа
              <input type="file" accept="image/*,video/*" style={{ display: 'none' }} onChange={handleMediaUpload} />
            </label>
            {mediaFile && (
              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                📎 {mediaFile.name}
                <button style={{ background: 'none', border: 'none', color: 'var(--neon-red)', cursor: 'pointer', marginLeft: '6px' }} onClick={() => setMediaFile(null)}>✕</button>
              </span>
            )}
          </div>
        </div>

        {/* Limits */}
        <div className="card section">
          <div className="card-header"><span className="card-title">⚙️ Налаштування розсилки</span></div>
          <div className="form-grid cols-3">
            {sendType === 'users' ? (
              <div className="input-group">
                <label className="input-label">Повідомлень з 1 акаунта</label>
                <div className="range-group">
                  <input type="range" min="5" max="50" value={limit} onChange={e => setLimit(+e.target.value)} />
                  <span className="range-value">{limit}</span>
                </div>
              </div>
            ) : (
              <div className="input-group">
                <label className="input-label">Інтервал повтору (хв)</label>
                <div className="range-group">
                  <input type="range" min="5" max="120" value={repeatInterval} onChange={e => setRepeatInterval(+e.target.value)} />
                  <span className="range-value">{repeatInterval} хв</span>
                </div>
              </div>
            )}
            
            <div className="input-group">
              <label className="input-label">Мін. затримка (сек)</label>
              <div className="range-group">
                <input type="range" min="10" max="180" value={delayMin} onChange={e => setDelayMin(+e.target.value)} />
                <span className="range-value">{delayMin}с</span>
              </div>
            </div>
            <div className="input-group">
              <label className="input-label">Макс. затримка (сек)</label>
              <div className="range-group">
                <input type="range" min="30" max="300" value={delayMax} onChange={e => setDelayMax(+e.target.value)} />
                <span className="range-value">{delayMax}с</span>
              </div>
            </div>
          </div>
        </div>

        {/* Auto-responder */}
        <div className="card section" style={{ display: sendType === 'users' ? 'block' : 'none' }}>
          <div className="card-header">
            <span className="card-title">🤖 Автовідповідач</span>
            <div className={`toggle-switch ${autoResponder ? 'on' : ''}`} onClick={() => setAutoResponder(!autoResponder)} />
          </div>
          {autoResponder && (
            <div className="form-grid">
              <div className="input-group">
                <label className="input-label">Ключові слова (через кому)</label>
                <input className="input" value={keywords} onChange={e => setKeywords(e.target.value)} />
              </div>
              <div className="input-group">
                <label className="input-label">Пересилати діалоги на</label>
                <input className="input" value={forwardTo} onChange={e => setForwardTo(e.target.value)} placeholder="@username або ID" />
              </div>
            </div>
          )}
        </div>

        {/* Status */}
        {sending && (
          <div className="card" style={{ borderColor: 'rgba(0,170,255,0.3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span className="badge running"><span className="badge-dot"></span> Розсилка активна</span>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                {sendType === 'chats' ? 'Надсилається по колу. ' : ''}
                Відправлено: <strong style={{ color: 'var(--neon-green)' }}>{sentCount}</strong>
                {sendType === 'users' ? ` / ${baseCount}` : ''} |
                Помилок: <strong style={{ color: 'var(--neon-red)' }}>{errorCount}</strong>
              </span>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
