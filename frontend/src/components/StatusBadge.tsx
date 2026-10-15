import type { DocumentStatus } from '../Type'

interface StatusBadgeProps {
  status: DocumentStatus
}

const statusStyles: Record<DocumentStatus, string> = {
  pending: 'badge-gray',
  uploading: 'badge-blue',
  processing: 'badge-orange',
  ready: 'badge-green',
  failed: 'badge-red'
}

function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`status-badge ${statusStyles[status]}`}>
      {status}
    </span>
  )
}

export default StatusBadge