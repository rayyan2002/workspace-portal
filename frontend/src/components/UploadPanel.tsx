import { useState, useRef } from 'react'
import { UploadCloud, AlertCircle } from 'lucide-react'
import type { Document, APIError } from '../Type'
import { MAX_FILE_SIZE_BYTES, ALLOWED_MIME_TYPES } from '../Type'
import { apiFetch } from '../api/client'

interface UploadPanelProps {
  onUploadSuccess: (doc: Document) => void
  acceptedExtensionsText?: string
  maxFileSizeText?: string
}

function UploadPanel({ 
  onUploadSuccess,
  acceptedExtensionsText = 'PDF, TXT, DOCX, MD, CSV, or XLSX',
  maxFileSizeText = '10MB'
}: UploadPanelProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const fileInputRef = useRef<HTMLInputElement>(null)

  /* ========================================================================
     1. Unified Upload Engine
     ======================================================================== */
  const processFile = async (file: File) => {
    setError(null)

    if (file.size > MAX_FILE_SIZE_BYTES) {
      setError('File exceeds the 10MB limit.')
      return
    }

    const fallbackExtensions = ['.md', '.markdown', '.csv', '.xlsx']
    const hasValidExtension = fallbackExtensions.some(ext => file.name.toLowerCase().endsWith(ext))
    const isValidType = ALLOWED_MIME_TYPES.includes(file.type) || hasValidExtension

    if (!isValidType) {
      setError('Unsupported file format. Please upload PDF, TXT, DOCX, MD, CSV, or XLSX.')
      return
    }

    setIsUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await apiFetch('/api/documents/upload', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        const errData = (await response.json().catch(() => ({}))) as APIError
        throw new Error(errData.message || 'Upload failed.')
      }

      const newDoc = (await response.json()) as Document
      onUploadSuccess(newDoc)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred during upload.')
    } finally {
      setIsUploading(false)
    }
  }

  /* ========================================================================
     2. Event Dispatchers (Browse vs. Drop)
     ======================================================================== */
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      processFile(file)
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    
    const file = e.dataTransfer.files?.[0]
    if (file) {
      processFile(file)
    }
  }

  /* ========================================================================
     3. Bulletproof Drag State Handlers
     ======================================================================== */
  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false)
    }
  }

  return (
    <div className="upload-panel-container">
      {error && (
        <div className="upload-error-banner" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Restored exact CSS classes from your UI pass */}
      <div 
        className={`upload-card-zone ${isDragging ? 'active-drag' : ''} ${isUploading ? 'uploading' : ''}`}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="upload-icon-wrapper">
          <UploadCloud size={20} />
        </div>
        
        {isUploading ? (
          <>
            <p className="upload-action-text">Uploading document...</p>
            <p className="upload-hint-sub">Please wait while we process the file.</p>
          </>
        ) : (
          <>
            <p className="upload-action-text">
              Drag and drop files here, or{' '}
              <label htmlFor="file-upload-input" className="browse-files-link">
                browse files
              </label>
            </p>
            <p className="upload-hint-sub">Supports {acceptedExtensionsText} up to {maxFileSizeText}</p>
          </>
        )}

        {/* Input mapped via ID, hidden via accessibility CSS */}
        <input
          id="file-upload-input"
          type="file"
          ref={fileInputRef}
          className="visually-hidden-input"
          onChange={handleFileChange}
          disabled={isUploading}
          accept=".pdf,.txt,.docx,.md,.markdown,.csv,.xlsx,application/pdf,text/plain,text/csv"
        />
      </div>
    </div>
  )
}

export default UploadPanel