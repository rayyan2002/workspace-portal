import { NavLink } from 'react-router';
import { LayoutDashboard, FileText, MessageSquare, Zap, Settings } from 'lucide-react';
import type { NavLink as NavLinkType } from './Type';
import './styles/layout.css';

interface SidebarProps {
  links: NavLinkType[];
}

function Sidebar({ links }: SidebarProps) {
  // Map icons safely by exact path key configuration
  const iconMap: Record<string, React.ComponentType<{ className?: string; size?: number }>> = {
    '/dashboard': LayoutDashboard,
    '/documents': FileText,
    '/chat': MessageSquare,
    '/actions': Zap,
    '/settings': Settings,
  };

  return (
    <nav className="app-sidebar">
      <div className="sidebar-group">
        {/* Single clean label - no duplication */}
        <span className="sidebar-group-label">Workspace</span>
        <ul className="sidebar-links">
          {links.map((link) => {
            const Icon = iconMap[link.to] || Settings;
            return (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  className={({ isActive }) =>
                    `sidebar-nav-item ${isActive ? 'active' : ''}`
                  }
                >
                  <Icon className="sidebar-nav-icon" size={16} />
                  <span>{link.label}</span>
                </NavLink>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}

export default Sidebar;