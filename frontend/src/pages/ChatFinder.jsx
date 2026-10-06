import { useState } from 'react'
import { Search, Download, Trash2, ExternalLink, Copy, Users, Hash, Filter } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function ChatFinder() {
  const [keywords, setKeywords] = useState('')
  const [minMembers, setMinMembers] = useState(0)
  const [limit, setLimit] = useState(50)
  const [chatType, setChatType] = useState('all') // 'all' | 'groups' | 'channels'
  const [searching, setSearching] = useState(false)
  const [chats, setChats] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [saved, setSaved] = useState(false)
  const [stats, setStats] = useState(null)

  const handleSearch = async () => {
    if (!keywords.trim()) return alert('Введіть ключові слова')
    setSearching(true)
    setSaved(false)
    setStats(null)
    try {
      const form = new FormData()
      form.append('keywords', keywords)
      form.append('min_members', minMembers)
      form.append('limit', limit)
      form.append('chat_type', chatType)
      const res = await fetch(`${API}/api/chat-finder/search`, { method: 'POST', body: form })
      if (res.ok) {
        const data = await res.json()
        setChats(data.chats || [])
        setSelected(new Set(data.chats.map(c => c.id)))
        setStats({ groups: data.groups_count, channels: data.channels_count, total: data.total })
      } else {
        const err = await res.json()
        alert(err.detail || 'Помилка пошуку')
      }
    } catch { alert('Бекенд не запущено') }
    setSearching(false)
  }

  const toggleSelect = (id) => {
    const s = new Set(selected)
    s.has(id) ? s.delete(id) : s.add(id)
    setSelected(s)
  }

  const toggleAll = () => {
    selected.size === chats.length ? setSelected(new Set()) : setSelected(new Set(chats.map(c => c.id)))
  }

  const handleExport = () => { window.open(`${API}/api/chat-finder/export`, '_blank') }

  const handleSave = async () => {
    const ids = selected.size === chats.length ? 'all' : [...selected].join(',')
    try {
      const form = new FormData()
      form.append('chat_ids', ids)
      const res = await fetch(`${API}/api/chat-finder/save`, { method: 'POST', body: form })
      if (res.ok) {
        const data = await res.json()
        setSaved(true)
        alert(`✅ Збережено ${data.count} посилань у файл:\n${data.filename}`)
      }
    } catch { alert('Бекенд не запущено') }
  }

  const handleClear = async () => {
    setChats([]); setSelected(new Set()); setSaved(false); setStats(null)
    try { await fetch(`${API}/api/chat-finder/clear`, { method: 'DELETE' }) } catch {}
  }

  const copyLinks = () => {
    const links = chats.filter(c => selected.has(c.id) && c.link).map(c => c.link).join('\n')
    navigator.clipboard.writeText(links)
    alert(`📋 Скопійовано ${links.split('\n').length} посилань!`)
  }

  const typeFilterOptions = [
    { value: 'all', label: '🌐 Все', desc: 'Чати + Канали' },
    { value: 'groups', label: '💬 Тільки чати', desc: 'Групи та супергрупи' },
    { value: 'channels', label: '📢 Тільки канали', desc: 'Канали' },
  ]

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Chat Finder</h2>
          <p className="subtitle">Пошук чатів, груп та каналів по ключовим словам</p>
        </div>
        <div className="btn-group">
          {chats.length > 0 && (
            <>
              <button className="btn btn-secondary btn-sm" onClick={copyLinks}><Copy size={14} /> Копіювати</button>
              <button className="btn btn-secondary btn-sm" onClick={handleExport}><Download size={14} /> Export .txt</button>
              <button className="btn btn-primary btn-sm" onClick={handleSave}><Download size={14} /> Зберегти файл</button>
            </>
          )}
        </div>
      </div>
      <div className="page-body">
        {/* Search form */}
        <div className="card section">
          <div className="card-header">
            <span className="card-title"><Search size={15} /> Пошук</span>
          </div>
          <div className="input-group">
            <label className="input-label">Ключові слова (через кому)</label>
            <input className="input" placeholder="крипта, трафік, арбітраж, CPA, партнерка"
              value={keywords} onChange={e => setKeywords(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()} />
          </div>

          {/* Type filter — tabs */}
          <div style={{ marginTop: '16px' }}>
            <label className="input-label" style={{ marginBottom: '8px', display: 'block' }}>
              <Filter size={12} style={{ verticalAlign: 'middle', marginRight: '4px' }} /> Тип результатів
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              {typeFilterOptions.map(opt => (
                <button key={opt.value}
                  className={`btn btn-sm ${chatType === opt.value ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setChatType(opt.value)}
                  style={{ flex: 1, flexDirection: 'column', padding: '10px 12px', height: 'auto', gap: '2px' }}>
                  <span style={{ fontSize: '14px' }}>{opt.label}</span>
                  <span style={{ fontSize: '10px', opacity: 0.7, fontWeight: 400 }}>{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="form-grid cols-3" style={{ marginTop: '16px' }}>
            <div className="input-group">
              <label className="input-label">Мін. учасників</label>
              <input className="input" type="number" min="0" value={minMembers}
                onChange={e => setMinMembers(+e.target.value)} placeholder="0" />
            </div>
            <div className="input-group">
              <label className="input-label">Ліміт</label>
              <div className="range-group">
                <input type="range" min="10" max="200" value={limit} onChange={e => setLimit(+e.target.value)} />
                <span className="range-value">{limit}</span>
              </div>
            </div>
            <div className="input-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button className="btn btn-primary" onClick={handleSearch} disabled={searching} style={{ width: '100%' }}>
                {searching ? <><span className="badge-dot" style={{ marginRight: '6px' }}></span> Пошук...</>
                  : <><Search size={15} /> Знайти</>}
              </button>
            </div>
          </div>
        </div>

        {/* Stats bar */}
        {stats && (
          <div style={{ display: 'flex', gap: '12px', padding: '4px 0' }}>
            <div className="card" style={{ flex: 1, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '20px' }}>🌐</span>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 600, color: 'var(--neon-green)' }}>{stats.total}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Всього</div>
              </div>
            </div>
            <div className="card" style={{ flex: 1, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '20px' }}>💬</span>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 600, color: 'var(--accent)' }}>{stats.groups}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Чати/Групи</div>
              </div>
            </div>
            <div className="card" style={{ flex: 1, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '20px' }}>📢</span>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 600, color: 'var(--neon-yellow)' }}>{stats.channels}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Канали</div>
              </div>
            </div>
          </div>
        )}

        {/* Results table */}
        {chats.length > 0 && (
          <div className="card">
            <div className="card-header">
              <span className="card-title">
                <Hash size={15} /> Результати
                {selected.size > 0 && selected.size < chats.length && (
                  <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: '8px' }}>
                    ({selected.size} обрано)
                  </span>
                )}
              </span>
              <div className="btn-group">
                <button className="btn btn-secondary btn-sm" onClick={toggleAll}>
                  {selected.size === chats.length ? 'Зняти все' : 'Обрати все'}
                </button>
                <button className="btn btn-danger btn-sm" onClick={handleClear}>
                  <Trash2 size={13} /> Очистити
                </button>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: '36px' }}>✓</th>
                    <th>Тип</th>
                    <th>Назва</th>
                    <th>Посилання</th>
                    <th>Учасники</th>
                    <th>Ключове слово</th>
                  </tr>
                </thead>
                <tbody>
                  {chats.map(chat => (
                    <tr key={chat.id} style={{ opacity: selected.has(chat.id) ? 1 : 0.4 }}>
                      <td>
                        <div className={`toggle-switch ${selected.has(chat.id) ? 'on' : ''}`}
                          onClick={() => toggleSelect(chat.id)} style={{ transform: 'scale(0.7)' }} />
                      </td>
                      <td>
                        <span className="badge" style={{
                          background: chat.type === 'group' ? 'rgba(139,92,246,0.15)' : 'rgba(250,204,21,0.15)',
                          color: chat.type === 'group' ? 'var(--accent)' : 'var(--neon-yellow)',
                          border: `1px solid ${chat.type === 'group' ? 'rgba(139,92,246,0.3)' : 'rgba(250,204,21,0.3)'}`,
                          whiteSpace: 'nowrap',
                        }}>
                          {chat.type_label}
                        </span>
                      </td>
                      <td style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{chat.title}</td>
                      <td>
                        {chat.link ? (
                          <a href={chat.link} target="_blank" rel="noreferrer"
                            style={{ color: 'var(--accent)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            {chat.link.replace('https://t.me/', '@')}
                            <ExternalLink size={11} />
                          </a>
                        ) : (
                          <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Приватний</span>
                        )}
                      </td>
                      <td>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Users size={12} style={{ color: 'var(--text-muted)' }} />
                          {chat.members ? chat.members.toLocaleString() : '—'}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{chat.keyword}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {saved && (
              <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', fontSize: '13px', color: 'var(--neon-green)' }}>
                ✅ Файл збережено у папку <strong>backend/exports/</strong>
              </div>
            )}
          </div>
        )}

        {/* Info */}
        {chats.length === 0 && !searching && (
          <>
            <div className="card section" style={{ borderLeft: '3px solid var(--accent)' }}>
              <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                <strong style={{ color: 'var(--accent)' }}>💡 Як використовувати:</strong><br />
                1. Введіть ключові слова через кому<br />
                2. Оберіть тип: <strong>💬 Чати</strong> (для інвайтингу/парсингу) або <strong>📢 Канали</strong> (для моніторингу)<br />
                3. Натисніть "Знайти" → оберіть потрібні → збережіть у файл<br />
                4. Використайте файл у <strong>Parser</strong>, <strong>Sender</strong> або <strong>Inviter</strong>
              </div>
            </div>
            <div className="card">
              <div className="empty-state">
                <div className="empty-state-icon">🔎</div>
                <div className="empty-state-text">Введіть ключові слова для пошуку</div>
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginTop: '8px' }}>
                  Наприклад: крипта, арбітраж, трафік, CPA
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
