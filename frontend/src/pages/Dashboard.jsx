import { useState, useEffect, useRef } from 'react'
import { Users, Send, UserPlus, AlertTriangle, Search, Activity, RefreshCw } from 'lucide-react'
import { API } from '../apiConfig'

export default function Dashboard() {
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const logRef = useRef(null)

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API}/api/dashboard/stats`)
      if (res.ok) {
        const data = await res.json()
        setStats(data)
      }
    } catch {
      // Backend not running — show zeroed stats
      setStats({
        active_accounts: 0, total_accounts: 0,
        spam_blocked: 0, banned: 0, total_parsed_users: 0,
        today: { messages_sent: 0, invites_sent: 0, users_parsed: 0, errors_count: 0 }
      })
    }
    setLoading(false)
  }

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${API}/api/dashboard/logs?limit=50`)
      if (res.ok) {
        const data = await res.json()
        setLogs(data.logs.reverse().map(l => ({
          time: l.created_at ? new Date(l.created_at).toLocaleTimeString('uk-UA') : '--:--:--',
          level: l.level || 'info',
          msg: l.message,
        })))
      }
    } catch {
      // Backend not running — empty logs
    }
  }

  useEffect(() => {
    fetchStats()
    fetchLogs()
    const interval = setInterval(() => { fetchStats(); fetchLogs() }, 5000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  const statCards = stats ? [
    { label: 'Активні акаунти', value: stats.active_accounts, icon: Users, color: 'purple' },
    { label: 'Відправлено сьогодні', value: stats.today.messages_sent, icon: Send, color: 'green' },
    { label: 'Запрошено сьогодні', value: stats.today.invites_sent, icon: UserPlus, color: 'blue' },
    { label: 'Спарсено юзерів', value: stats.total_parsed_users, icon: Search, color: 'yellow' },
    { label: 'Spam-block', value: stats.spam_blocked, icon: AlertTriangle, color: 'red' },
  ] : []

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Dashboard</h2>
          <p className="subtitle">Головна панель моніторингу</p>
        </div>
        <div className="btn-group">
          <button className="btn btn-secondary btn-sm" onClick={() => { fetchStats(); fetchLogs() }}>
            <RefreshCw size={14} /> Оновити
          </button>
        </div>
      </div>
      <div className="page-body">
        {loading ? (
          <div className="empty-state">
            <div className="empty-state-icon">⏳</div>
            <div className="empty-state-text">Завантаження...</div>
          </div>
        ) : (
          <>
            <div className="stats-grid">
              {statCards.map((s, i) => (
                <div className={`stat-card ${s.color}`} key={i}>
                  <div className={`stat-icon ${s.color}`}><s.icon size={20} /></div>
                  <div className="stat-value">{typeof s.value === 'number' ? s.value.toLocaleString() : s.value}</div>
                  <div className="stat-label">{s.label}</div>
                </div>
              ))}
            </div>

            <div className="section">
              <div className="section-title">
                <Activity size={16} /> Лог подій (реальний час)
              </div>
              <div className="log-terminal">
                <div className="log-terminal-header">
                  <span className="terminal-dot red"></span>
                  <span className="terminal-dot yellow"></span>
                  <span className="terminal-dot green"></span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '8px' }}>phantom_harvester.log</span>
                </div>
                <div className="log-terminal-body" ref={logRef}>
                  {logs.length === 0 ? (
                    <div className="log-entry">
                      <span className="log-time">[--:--:--]</span>
                      <span className="log-level info">INFO</span>
                      <span className="log-msg">Очікування подій... Запустіть бекенд для отримання логів.</span>
                    </div>
                  ) : (
                    logs.map((log, i) => (
                      <div className="log-entry" key={i}>
                        <span className="log-time">[{log.time}]</span>
                        <span className={`log-level ${log.level}`}>{log.level.toUpperCase()}</span>
                        <span className="log-msg">{log.msg}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
