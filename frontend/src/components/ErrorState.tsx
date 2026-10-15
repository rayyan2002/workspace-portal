import type { ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface ErrorStateProps {
  title?: string
  message: string
  action?: ReactNode
}

export default function ErrorState({ 
  title = 'Failed to load data', 
  message, 
  action 
}: ErrorStateProps) {
  return (
    <div className="page-state-container">
      <div className="page-state-icon error">
        <AlertTriangle size={32} />
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