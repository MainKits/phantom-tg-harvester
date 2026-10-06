import { useState, useEffect } from 'react'
import { Download, Upload, Zap, Video, AlertCircle, CheckCircle2, Share2, Send } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function MediaTools() {
  const [activeTab, setActiveTab] = useState('tiktok')
  const [tiktokUrl, setTiktokUrl] = useState('')
  const [tiktokData, setTiktokData] = useState(null)
  const [tiktokLoading, setTiktokLoading] = useState(false)
  const [tiktokError, setTiktokError] = useState(null)

  const [uploadFile, setUploadFile] = useState(null)
  const [aggressiveness, setAggressiveness] = useState(1)
  const [frameStyle, setFrameStyle] = useState('none')
  const [uniqLoading, setUniqLoading] = useState(false)
  const [uniqError, setUniqError] = useState(null)
  const [uniqSuccessUrl, setUniqSuccessUrl] = useState(null)

  // Auto-post state
  const [autoPost, setAutoPost] = useState(false)
  const [ttAccounts, setTtAccounts] = useState([])
  const [selectedAccs, setSelectedAccs] = useState([])
  const [description, setDescription] = useState('')
  const [postingStatus, setPostingStatus] = useState(null)

  useEffect(() => {
    fetchTtAccounts()
  }, [])

  const fetchTtAccounts = async () => {
    try {
      const res = await fetch(`${API}/api/tiktok/accounts`)
      const data = await res.json()
      setTtAccounts(data)
    } catch {}
  }

  const toggleAccount = (id) => {
    setSelectedAccs(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  const fetchTiktok = async () => {
    if (!tiktokUrl) return
    setTiktokLoading(true)
    setTiktokError(null)
    setTiktokData(null)
    try {
      const res = await fetch(`${API}/api/media/tiktok-info?url=${encodeURIComponent(tiktokUrl)}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Error fetching video')
      setTiktokData(data)
    } catch (err) {
      setTiktokError(err.message)
    } finally {
      setTiktokLoading(false)
    }
  }

  const handleUniqualize = async () => {
    if (!uploadFile) return
    setUniqLoading(true)
    setUniqError(null)
    setUniqSuccessUrl(null)
    setPostingStatus(null)
    
    const formData = new FormData()
    formData.append('file', uploadFile)
    formData.append('aggressiveness', aggressiveness)
    formData.append('frame_style', frameStyle)

    if (autoPost && selectedAccs.length > 0) {
      formData.append('description', description)
      formData.append('account_ids', JSON.stringify(selectedAccs))
      
      try {
        const res = await fetch(`${API}/api/tiktok/auto-post`, {
          method: 'POST',
          body: formData
        })
        if (res.ok) {
          setPostingStatus('Завдання на автопостинг успішно створено! Відео будуть унікалізовані та виставлені по черзі.')
          setUniqLoading(false)
          return
        } else {
          const err = await res.json()
          throw new Error(err.detail || 'Failed to start auto-post')
        }
      } catch (err) {
        setUniqError(err.message)
        setUniqLoading(false)
        return
      }
    }

    try {
      const res = await fetch(`${API}/api/media/uniqualize`, {
        method: 'POST',
        body: formData
      })
      if (!res.ok) {
        const errorData = await res.json()
        throw new Error(errorData.detail || 'Failed to process media')
      }
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      setUniqSuccessUrl(url)
    } catch (err) {
      setUniqError(err.message)
    } finally {
      setUniqLoading(false)
    }
  }

  return (
    <div className="page-container fade-in">
      <header className="page-header">
        <h1>Media Studio (TikTok)</h1>
        <p>Завантажуй без водяних знаків та унікалізуй відео для обходу тіньового бану.</p>
      </header>

      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '20px', borderBottom: '1px solid #333', paddingBottom: '10px' }}>
          <button className={`btn ${activeTab === 'tiktok' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setActiveTab('tiktok')}><Download size={18} /> TikTok Downloader</button>
          <button className={`btn ${activeTab === 'uniqualizer' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setActiveTab('uniqualizer')}><Zap size={18} /> Унікалізатор (Uniqualizer)</button>
        </div>
      </div>

      {activeTab === 'tiktok' && (
        <div className="card">
          <h2>Завантаження TikTok без водяних знаків</h2>
          {tiktokError && <div className="alert alert-error"><AlertCircle size={20} />{tiktokError}</div>}
          <div style={{ display: 'flex', gap: '10px', marginTop: '15px' }}>
            <input type="text" className="input" placeholder="Встав посилання на TikTok відео..." value={tiktokUrl} onChange={e => setTiktokUrl(e.target.value)} style={{ flex: 1 }} />
            <button className="btn btn-primary" onClick={fetchTiktok} disabled={tiktokLoading}>{tiktokLoading ? 'Пошук...' : 'Отримати відео'}</button>
          </div>
          {tiktokData && (
            <div style={{ marginTop: '30px', display: 'flex', gap: '20px', background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '12px' }}>
              <img src={tiktokData.cover} alt="Cover" style={{ width: '150px', borderRadius: '8px', objectFit: 'cover' }} />
              <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                <h3 style={{ margin: '0 0 10px 0' }}>{tiktokData.title}</h3>
                <p style={{ margin: '0 0 20px 0', color: '#a0a0a0' }}>Автор: @{tiktokData.author}</p>
                <a href={tiktokData.play_url} target="_blank" rel="noreferrer" className="btn btn-success" style={{ width: 'fit-content', display: 'flex', alignItems: 'center', gap: '8px', textDecoration: 'none' }}><Download size={18} /> Завантажити MP4</a>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'uniqualizer' && (
        <div className="card">
          <h2>Унікалізація та Автопостинг</h2>
          {uniqError && <div className="alert alert-error"><AlertCircle size={20} />{uniqError}</div>}
          {postingStatus && <div className="alert alert-success"><CheckCircle2 size={20} />{postingStatus}</div>}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div className="form-group">
              <label>Виберіть файл (MP4, MOV)</label>
              <div style={{ border: '2px dashed #444', padding: '40px', borderRadius: '12px', textAlign: 'center', background: 'rgba(0,0,0,0.2)' }}>
                <Video size={40} style={{ color: '#888', marginBottom: '10px' }} />
                <br />
                <input type="file" accept="video/mp4,video/quicktime" onChange={e => setUploadFile(e.target.files[0])} style={{ color: '#fff' }} />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '20px' }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Рівень агресивності</label>
                <select className="input" value={aggressiveness} onChange={e => setAggressiveness(parseInt(e.target.value))}>
                  <option value={1}>Легкий</option>
                  <option value={2}>Середній</option>
                  <option value={3}>Максимальний</option>
                </select>
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Додати AI-рамку</label>
                <select className="input" value={frameStyle} onChange={e => setFrameStyle(e.target.value)}>
                  <option value="none">Без рамки</option>
                  <option value="blur">Blur Style</option>
                  <option value="neon">Neon Cyberpunk</option>
                  <option value="casino">Casino Luxury</option>
                </select>
              </div>
            </div>

            <div className="form-group" style={{ background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '12px', border: '1px solid #333' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontSize: '16px', fontWeight: 'bold', color: '#00f2ea' }}>
                <input type="checkbox" checked={autoPost} onChange={e => setAutoPost(e.target.checked)} style={{ width: '20px', height: '20px' }} />
                <Share2 size={20} /> Автоматично виставити в TikTok
              </label>
              
              {autoPost && (
                <div className="fade-in" style={{ marginTop: '20px' }}>
                  <label>Виберіть акаунти ({selectedAccs.length} вибрано):</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginTop: '10px' }}>
                    {ttAccounts.map(acc => (
                      <div 
                        key={acc.id} 
                        onClick={() => toggleAccount(acc.id)}
                        style={{ 
                          padding: '8px 15px', 
                          borderRadius: '20px', 
                          border: `1px solid ${selectedAccs.includes(acc.id) ? '#00f2ea' : '#444'}`,
                          background: selectedAccs.includes(acc.id) ? 'rgba(0, 242, 234, 0.1)' : 'transparent',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          transition: 'all 0.2s'
                        }}
                      >
                        <User size={14} /> {acc.username}
                      </div>
                    ))}
                    {ttAccounts.length === 0 && <p style={{ color: '#888', fontSize: '13px' }}>Спочатку додайте акаунти в "TikTok Manager"</p>}
                  </div>

                  <div className="form-group" style={{ marginTop: '20px' }}>
                    <label>Опис та хештеги</label>
                    <textarea 
                      className="input" 
                      rows="4" 
                      placeholder="Ваш текст... #fyp #viral" 
                      value={description}
                      onChange={e => setDescription(e.target.value)}
                    ></textarea>
                  </div>
                </div>
              )}
            </div>

            <button className="btn btn-primary" onClick={handleUniqualize} disabled={uniqLoading || !uploadFile} style={{ width: '100%', padding: '15px', fontSize: '16px' }}>
              {uniqLoading ? '⏳ Процес запущено...' : (autoPost ? <><Send size={20} /> Унікалізувати та Залити</> : <><Zap size={20} /> Унікалізувати файл</>)}
            </button>

            {uniqSuccessUrl && (
              <div style={{ marginTop: '20px', padding: '20px', background: 'rgba(46, 213, 115, 0.1)', border: '1px solid rgba(46, 213, 115, 0.3)', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><CheckCircle2 size={24} color="#2ed573" /><span style={{ color: '#2ed573', fontWeight: 'bold' }}>Успішно!</span></div>
                <a href={uniqSuccessUrl} download={`unique_${uploadFile?.name || 'media.mp4'}`} className="btn btn-success"><Download size={18} /> Скачати</a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
