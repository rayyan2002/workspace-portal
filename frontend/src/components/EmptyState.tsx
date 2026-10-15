import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  message: string
  action?: ReactNode
}

export default function EmptyState({ 
  icon,
  title, 
  message, 
  action 
}: EmptyStateProps) {
  return (
    <div className="page-state-container">
      <div className="page-state-icon empty">
        {icon}
      </div>
      <h2 className="page-state-title">{title}</h2>
      <p className="page-state-message">{message}</p>
      
      {action && (
        <div className="page-state-action">
          {action}
        </div>
      )}
    </div>
  )
}