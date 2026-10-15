import { useState } from 'react'
import { useParams, Link } from 'react-router'
import { PlusCircle } from 'lucide-react'
import SessionList from '../components/SessionList'
import MessageView from '../components/MessageView'
import '../styles/chat.css'

function ChatPage() {
  const { sessionId } = useParams()
  const [refreshKey, setRefreshKey] = useState(0)

  // If there's an ID (including 'new'), the message pane is active on mobile
  const isSessionActive = !!sessionId

  return (
    <div className={`chat-viewport-grid ${isSessionActive ? 'has-active-session' : ''}`}>
      <aside className="chat-sidebar-pane">
        <div className="sidebar-header">
          <h2>Conversations</h2>
          <Link to="/chat/new" className="btn-new-chat">
            <PlusCircle size={14} />
            <span>New Chat</span>
          </Link>
        </div>
        <SessionList 
          activeSessionId={sessionId || null} 
          refreshKey={refreshKey} 
        />
      </aside>

      <main className="chat-content-pane">
        {!sessionId ? (
          <div className="chat-empty-placeholder">
            <h3>Select or start a conversation to begin</h3>
          </div>
        ) : (
          <MessageView 
            sessionId={sessionId} 
            sessionTitle="Conversation"
            onSessionCreated={() => {
              // Trigger sidebar refresh, but let MessageView handle URL navigation
              setRefreshKey(k => k + 1)
            }}
          />
        )}
      </main>
    </div>
  )
}

export default ChatPage