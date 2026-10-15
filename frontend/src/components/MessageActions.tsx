import type { ActionProposal } from '../Type'
import ActionCard from './ActionCard'

interface MessageActionsProps {
  actions: ActionProposal[]
  sessionId: string
}

function MessageActions({ actions, sessionId }: MessageActionsProps) {
  if (!actions || actions.length === 0) return null
  return (
    <div className="message-actions-wrapper">
      {actions.map((act) => <ActionCard key={act.id} proposal={act} sessionId={sessionId} />)}
    </div>
  )
}
export default MessageActions