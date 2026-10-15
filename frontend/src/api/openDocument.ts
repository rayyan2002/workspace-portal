import { apiFetch } from './client'

/**
 * How a given file can be previewed in the page.
 *
 * Browsers decide what to do with a blob URL from its MIME type, and they only
 * RENDER a small set — PDFs and images. Anything else (markdown, CSV, DOCX, XLSX)
 * is treated as a file to save, so pointing an iframe at it silently triggers a
 * download instead of showing anything. Text-based formats are therefore read and
 * rendered by the app itself, and genuinely binary formats admit they cannot be
 * previewed rather than dumping a file into Downloads.
 */
export type PreviewKind = 'embed' | 'text' | 'unsupported'

const TEXT_EXTENSIONS = ['.md', '.markdown', '.txt', '.csv', '.json', '.log', '.yml', '.yaml']
const EMBED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']

export function previewKindFor(filename: string): PreviewKind {
  const name = filename.toLowerCase()

  if (EMBED_EXTENSIONS.some((ext) => name.endsWith(ext))) return 'embed'
  if (TEXT_EXTENSIONS.some((ext) => name.endsWith(ext))) return 'text'

  // .docx, .xlsx and friends: no browser renders these, and no amount of MIME
  // coaxing changes that. Saying so is better than appearing to do nothing.
  return 'unsupported'
}

/**
 * Fetches a document's original bytes.
 *
 * A plain `<a href>` or `<iframe src>` pointing at the API cannot work: the endpoint
 * is authenticated by an `Authorization` header, and a browser-initiated request
 * sends no such header — it would arrive unauthenticated and 401.
 */
async function fetchDocumentBlob(documentId: string): Promise<Blob> {
  const response = await apiFetch(`/api/documents/${documentId}/download`)

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.message || 'The original file could not be opened.')
  }

  return response.blob()
}

/** An object URL for formats the browser renders natively (PDF, images). */
export async function fetchDocumentObjectUrl(documentId: string): Promise<string> {
  return URL.createObjectURL(await fetchDocumentBlob(documentId))
}

/** The decoded contents of a text-based document, rendered by us, not the browser. */
export async function fetchDocumentText(documentId: string): Promise<string> {
  return (await fetchDocumentBlob(documentId)).text()
}

/**
 * Saves a document to disk. Only ever called when the user explicitly asks —
 * viewing a file must never deposit a copy in someone's Downloads folder, least of
 * all a file they already have.
 */
export async function downloadDocument(documentId: string, filename: string): Promise<void> {
  const objectUrl = URL.createObjectURL(await fetchDocumentBlob(documentId))

  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()

  // Revoked on a timer rather than at once, which can race the browser's read.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
}
