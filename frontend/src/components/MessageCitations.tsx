import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { Citation } from '../Type'
import CitationCard from './CitationCard'

interface MessageCitationsProps {
  citations: Citation[]
}

function MessageCitations({ citations }: MessageCitationsProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!citations || citations.length === 0) return null

  return (
    <div className="message-citations-wrapper">
      <button 
        type="button" 
        className="btn-citation-toggle"
        onClick={() => setIsExpanded(prev => !prev)}
      >
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>Sources ({citations.length})</span>
      </button>

      {isExpanded && (
        <div className="citations-tray">
          {citations.map((citation) => (
            <CitationCard key={citation.id} citation={citation} />
          ))}
        </div>
      )}
    </div>
  )
}

export default MessageCitations