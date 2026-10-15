import { Link } from 'react-router'
import { FileText } from 'lucide-react'
import type { Citation } from '../Type'

interface CitationCardProps {
  citation: Citation
}

function CitationCard({ citation }: CitationCardProps) {
  return (
    <div className="citation-card">
      <div className="citation-header">
        <FileText size={14} className="citation-icon" />
        <Link to={`/documents/${citation.documentId}`} className="citation-link">
          {citation.documentName}
        </Link>
      </div>
      
      {/*
        Section OR page, whichever the document actually has. Measured on the real corpus:
        80 of 177 chunks carry a heading and 55 carry a page, and they are largely
        complementary — the PDFs that dominate real citations have a page and no heading, so
        a card showing only `section` rendered nothing at all for them.
      */}
      {(citation.section || citation.page != null) && (
        <div className="citation-section">
          {citation.section || `Page ${citation.page}`}
        </div>
      )}

      <blockquote className="citation-excerpt">
        "{citation.excerpt}"
      </blockquote>

      {/*
        A word, not a number. It measures how closely this passage matched the QUESTION, not
        whether the answer is right — and a percentage next to a generated answer would read
        as confidence in the answer. The title attribute says which it is.
      */}
      {citation.matchQuality && (
        <div className="citation-quality" title="How closely this passage matched your question">
          {citation.matchQuality}
        </div>
      )}
    </div>
  )
}

export default CitationCard