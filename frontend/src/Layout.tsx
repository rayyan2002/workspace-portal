import { useState, useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router'
import { Menu } from 'lucide-react'
import { useAuth } from './context/AuthContext'
import Header from './Header'
import Sidebar from './Sidebar'
import ErrorBoundary from './components/ErrorBoundary'
import type { NavLink } from './Type'
import './styles/layout.css'

const baseNavLinks: NavLink[] = [
  { label: 'Dashboard', to: '/dashboard' },
  { label: 'Documents', to: '/documents' },
  { label: 'Chat', to: '/chat' },
  { label: 'Actions', to: '/actions' },
  { label: 'Settings', to: '/settings' }
]

const adminNavLink: NavLink = { label: 'Admin', to: '/admin' }

export default function Layout() {
  const location = useLocation()
  const { hasRole } = useAuth()

  // Shown only to admins. This hides a door rather than locking one — the lock is
  // server-side, where /api/admin/** answers 403 whatever the client renders.
  const navLinks = hasRole('ROLE_ADMIN') ? [...baseNavLinks, adminNavLink] : baseNavLinks
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const hamburgerRef = useRef<HTMLButtonElement>(null)

  // 1. Close sidebar automatically when a user navigates
  useEffect(() => {
    setIsMobileMenuOpen(false)
  }, [location.pathname])

  // 2. Escape key management and initial focus
  useEffect(() => {
    if (!isMobileMenuOpen) return

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsMobileMenuOpen(false)
        hamburgerRef.current?.focus()
      }
    }

    document.addEventListener('keydown', handleEscape)

    const sidebarNode = document.querySelector('.app-sidebar') as HTMLElement
    const firstInteractiveElement = sidebarNode?.querySelector('a[href], button') as HTMLElement
    
    if (firstInteractiveElement) {
      firstInteractiveElement.focus()
    }

    return () => document.removeEventListener('keydown', handleEscape)
  }, [isMobileMenuOpen])

  // 3. THE TRAP: Bulletproof DOM-level inert toggling
  useEffect(() => {
    const main = document.querySelector('.main-content')
    const header = document.querySelector('.app-header')
    
    if (isMobileMenuOpen) {
      main?.setAttribute('inert', '')
      header?.setAttribute('inert', '')
    } else {
      main?.removeAttribute('inert')
      header?.removeAttribute('inert')
    }
    
    return () => {
      main?.removeAttribute('inert')
      header?.removeAttribute('inert')
    }
  }, [isMobileMenuOpen])

  return (
    <div className={`app-shell ${isMobileMenuOpen ? 'mobile-menu-open' : ''}`}>
      {/* Backdrop overlay */}
      {isMobileMenuOpen && (
        <div 
          className="sidebar-overlay"
          aria-hidden="true"
          onClick={() => {
            setIsMobileMenuOpen(false)
            hamburgerRef.current?.focus()
          }}
        />
      )}

      {/* The Drawer */}
      <Sidebar links={navLinks} />
      
      {/* SHELL CONTROL: The Hamburger now lives outside the inert zones */}
      <button 
        ref={hamburgerRef}
        className="mobile-hamburger-btn"
        // A real toggle. It already announced itself as "Close navigation menu" with
        // aria-expanded=true while open, but only ever set the state to true — so the
        // control described an action it could not perform, which is worse for a screen
        // reader user than having no label at all.
        onClick={() => setIsMobileMenuOpen((open) => !open)}
        aria-label={isMobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
        aria-expanded={isMobileMenuOpen}
      >
        <Menu size={20} />
      </button>

      {/* inert safely disables the header behind the overlay */}
      <header className="app-header">
        <Header />
      </header>

      {/* inert safely disables the main content behind the overlay */}
      <main className="main-content">
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}