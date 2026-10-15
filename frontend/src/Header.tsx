import { useNavigate } from 'react-router'
import { LogOut, LayoutGrid } from 'lucide-react'
import { useAuth } from './context/AuthContext'
import './styles/layout.css'

export default function Header() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  // Extract up to two initials from the user's name
  const getUserInitials = () => {
    if (!user?.name) return 'U'
    return user.name
      .split(' ')
      .map((part) => part.charAt(0))
      .slice(0, 2)
      .join('')
  }

  return (
    <div className="header-content-wrapper">
      {/* Brand logo and title */}
      <div className="header-brand">
        <LayoutGrid className="brand-logo" size={18} />
        <h2 className="brand-title">Workspace Portal</h2>
      </div>

      {/* User profile actions and logout */}
      <div className="header-actions">
        {user && (
          <div className="user-profile">
            <div className="user-avatar-badge" aria-hidden="true">
              {getUserInitials()}
            </div>
            <span className="user-name">{user.name}</span>
            
            <button 
              onClick={handleLogout} 
              className="logout-button"
              aria-label="Log out"
            >
              <LogOut className="logout-icon" size={14} />
              <span className="logout-text">Log out</span>
            </button>
          </div>
        )}
      </div>
    </div>
  )
}