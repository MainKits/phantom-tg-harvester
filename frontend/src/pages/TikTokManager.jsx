import { useState, useEffect } from 'react'
import { Plus, Trash2, Shield, User, Clock, AlertCircle } from 'lucide-react'

const API = 'http://127.0.0.1:8000'

export default function TikTokManager() {
  const [accounts, setAccounts] = useState([])
  const [username, setUsername] = useState('')
  const [cookies, setCookies] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchAccounts()
  }, [])

  const fetchAccounts = async () => {
    try {
      const res = await fetch(`${API}/api/tiktok/accounts`)
      const data = await res.json()
      setAccounts(data)
    } catch {}
  }

  const addAccount = async () => {
    if (!username || !cookies) return
    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('username', username)
      formData.append('cookies', cookies)
      
      const res = await fetch(`${API}/api/tiktok/accounts`, {
        method: 'POST',
        body: formData
      })
      if (res.ok) {
        setUsername('')
        setCookies('')
        fetchAccounts()
      } else {
        const err = await res.json()
        alert(err.detail || 'Failed to add account')
      }
    } catch (err) {
      alert(err.message)
    } finally {
      setLoading(false)
    }
  }

  const deleteAccount = async (id) => {
    if (!confirm('Ви впевнені?')) return
    try {
      await fetch(`${API}/api/tiktok/accounts/${id}`, { method: 'DELETE' })
      fetchAccounts()
    } catch {}
  }

  return (
    <div className="page-container fade-in">
      <header className="page-header">
        <h1>TikTok Account Manager</h1>
        <p>Керуйте своїми ТікТок акаунтами для автоматичного постінгу через Cookies.</p>
      </header>

      <div className="grid-2">
        <div className="card">
          <h2>Додати акаунт</h2>
          <p style={{ color: '#888', marginBottom: '20px', fontSize: '13px' }}>
            Експортуйте Cookies у форматі JSON за допомогою розширення EditThisCookie.
          </p>
          
          <div className="form-group">
            <label>Назва/Юзернейм</label>
            <input 
              type="text" 
              className="input" 
              placeholder="@username..." 
              value={username}
              onChange={e => setUsername(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>JSON Cookies</label>
            <textarea 
              className="input" 
              rows="8"
              placeholder='[{"domain": ".tiktok.com", "name": "sessionid", ...}]'
              value={cookies}
              onChange={e => setCookies(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: '11px' }}
            ></textarea>
          </div>

          <button 
            className="btn btn-primary" 
            style={{ width: '100%' }}
            onClick={addAccount}
            disabled={loading}
          >
            <Plus size={18} /> {loading ? 'Додавання...' : 'Додати TikTok Акаунт'}
          </button>
        </div>

        <div className="card">
          <h2>Ваші акаунти ({accounts.length})</h2>
          <div className="account-list" style={{ marginTop: '15px' }}>
            {accounts.map(acc => (
              <div key={acc.id} className="account-card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '15px', background: 'rgba(255,255,255,0.03)', borderRadius: '10px', marginBottom: '10px', border: '1px solid #333' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                  <div className="acc-avatar" style={{ width: '40px', height: '40px', background: 'linear-gradient(45deg, #ff0050, #00f2ea)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>
                    {acc.username[0].toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight: 'bold' }}>{acc.username}</div>
                    <div style={{ fontSize: '12px', color: '#888' }}>
                      <Clock size={12} inline /> Додано: {new Date(acc.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <div className={`status-badge ${acc.status === 'active' ? 'status-active' : 'status-error'}`}>
                    {acc.status}
                  </div>
                  <button className="btn btn-icon btn-danger" onClick={() => deleteAccount(acc.id)}>
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
            {accounts.length === 0 && (
              <div style={{ textAlign: 'center', padding: '40px', color: '#666' }}>
                Акаунти не знайдено. Додайте свій перший акаунт зліва.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
