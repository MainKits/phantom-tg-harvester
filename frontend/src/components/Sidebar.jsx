import { useState, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Users, Search, Send, UserPlus, Globe, Film, Shield, Key, Sparkles } from 'lucide-react'
import UpdateModal from './UpdateModal'

const API = 'http://127.0.0.1:8000'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/accounts', icon: Users, label: 'Account Manager' },
  { path: '/parser', icon: Search, label: 'Parser' },
  { path: '/chat-finder', icon: Globe, label: 'Chat Finder' },
  { path: '/sender', icon: Send, label: 'Sender' },
  { path: '/inviter', icon: UserPlus, label: 'Inviter' },
  { path: '/media-tools', icon: Film, label: 'Media Tools' },
  { path: '/tiktok-manager', icon: Shield, label: 'TikTok Manager' },
  { path: '/admin/license', icon: Key, label: '⚙️ License Admin' },
]

export default function Sidebar() {
  const [updateInfo, setUpdateInfo] = useState(null)
  const [isUpdateOpen, setIsUpdateOpen] = useState(false)

  const checkUpdates = async () => {
    try {
      const res = await fetch(`${API}/api/system/check-update`)
      if (res.ok) {
        const data = await res.json()
        setUpdateInfo(data)
      }
    } catch {}
  }

  useEffect(() => {
    checkUpdates()
  }, [])

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">👻</div>
          <h1>
            Phantom
            <span>TG Harvester</span>
          </h1>
        </div>

        <nav className="sidebar-nav">
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              end={item.path === '/'}
            >
              <item.icon className="nav-icon" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer" style={{ padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          {updateInfo?.has_update ? (
            <button
              onClick={() => setIsUpdateOpen(true)}
              style={{
                width: '100%',
                background: 'linear-gradient(135deg, rgba(132,0,255,0.2), rgba(0,200,255,0.2))',
                border: '1px solid var(--accent)',
                borderRadius: '8px',
                padding: '8px 10px',
                color: '#fff',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                animation: 'pulse 2s infinite',
              }}
            >
              <Sparkles size={14} color="var(--accent)" /> Оновлення v{updateInfo.latest_version}!
            </button>
          ) : (
            <div
              onClick={() => setIsUpdateOpen(true)}
              style={{
                fontSize: '12px',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                textAlign: 'center',
                transition: 'color 0.2s',
              }}
              title="Натисніть для перевірки оновлень"
            >
              Phantom Harvester v{updateInfo?.current_version || '1.0.0'}
            </div>
          )}
        </div>
      </aside>

      <UpdateModal
        isOpen={isUpdateOpen}
        onClose={() => setIsUpdateOpen(false)}
        updateInfo={updateInfo}
        onRefresh={checkUpdates}
      />
    </>
  )
}
