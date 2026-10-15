import { AlertTriangle, ExternalLink, X } from 'lucide-react'
import { Link } from 'react-router'
import type { DocumentDeletionImpact } from '../Type'

interface Props {
  impact: DocumentDeletionImpact
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
}

/**
 * The confirmation shown when deleting a document would also delete conversations.
 *
 * WHY THIS EXISTS. `citations.document_id` is ON DELETE RESTRICT, so the delete used to
 * fail on a foreign key and the user was shown "Failed to delete … The document has been
 * restored." True, and useless: it named no cause and offered no way forward, so the
 * document simply looked undeletable.
 *
 * EVERY NAME HERE IS A LINK, because the honest answer to "are you sure?" is usually "let
 * me look first". A conversation title you cannot open is a thing you are asked to destroy
 * sight unseen.
 *
 * THE OTHER DOCUMENTS SURVIVE, and the dialog says so outright. They are listed because a
 * conversation is not necessarily ABOUT the document being deleted — measured on the real
 * corpus, a ten-message chat titled "tell me about finance" cites four documents — so what
 * is actually lost is the DISCUSSION of them, not the material itself.
 */
export function DeleteDocumentDialog({ impact, busy, onConfirm, onCancel }: Props) {
  const count = impact.chats.length
  const totalMessages = impact.chats.reduce((n, c) => n + c.messageCount, 0)
  const survivors = new Map(
    impact.chats.flatMap((c) => c.otherDocuments).map((d) => [d.id, d]),
  )

  return (
    <div className="dialog-overlay" onClick={busy ? undefined : onCancel}>
      <div
        className="dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-doc-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-head">
          <AlertTriangle className="dialog-icon-warn" size={20} aria-hidden="true" />
          <h2 id="delete-doc-title">Delete “{impact.filename}”?</h2>
          {/* "Close", not "Cancel" — there is already a Cancel button below, and two
              controls sharing an accessible name is ambiguous to a screen reader and to
              anyone querying by name. */}
          <button className="dialog-close" onClick={onCancel} disabled={busy}
                  title="Close" aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <p className="dialog-lead">
          {count === 1
            ? 'This document is used by 1 conversation, which will also be deleted:'
            : `This document is used by ${count} conversations, which will also be deleted:`}
        </p>

        <ul className="dialog-chat-list">
          {impact.chats.map((chat) => (
            <li key={chat.id}>
              <Link
                to={`/chat/${chat.id}`}
                className="dialog-chat-title"
                title="Open this conversation"
                target="_blank"
                rel="noopener noreferrer"
              >
                {chat.title}
                <ExternalLink size={13} aria-hidden="true" />
              </Link>
              <span className="dialog-chat-meta">
                {chat.messageCount} {chat.messageCount === 1 ? 'message' : 'messages'}
                {chat.otherDocuments.length > 0 && (
                  <>
                    {' · also uses '}
                    {chat.otherDocuments.map((doc, i) => (
                      <span key={doc.id}>
                        {i > 0 && ', '}
                        <Link
                          to={`/documents/${doc.id}`}
                          className="dialog-doc-link"
                          title="Open this document"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {doc.filename}
                        </Link>
                      </span>
                    ))}
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>

        <p className="dialog-warning">
          {totalMessages} {totalMessages === 1 ? 'message' : 'messages'} will be permanently
          deleted. This cannot be undone.
        </p>

        {survivors.size > 0 && (
          // The question a person asks next, answered before they have to ask it.
          <p className="dialog-reassure">
            {survivors.size === 1 ? 'The other document' : 'The other documents'} named above
            {survivors.size === 1 ? ' is' : ' are'} <strong>not</strong> deleted — only{' '}
            “{impact.filename}” and {count === 1 ? 'this conversation' : 'these conversations'}.
          </p>
        )}

        <div className="dialog-actions">
          <button className="btn-dialog-cancel" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className="btn-dialog-danger" onClick={onConfirm} disabled={busy}>
            {busy
              ? 'Deleting…'
              : `Delete document and ${count} ${count === 1 ? 'conversation' : 'conversations'}`}
          </button>
        </div>
      </div>
    </div>
  )
}
