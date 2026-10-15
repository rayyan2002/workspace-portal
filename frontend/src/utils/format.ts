import { MAX_FILE_SIZE_BYTES, ALLOWED_MIME_TYPES } from '../Type'

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B'
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  const formattedValue = parseFloat((bytes / Math.pow(k, i)).toFixed(1))
  return `${formattedValue} ${sizes[i]}`
}

export function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

export function validateFile(file: File): string | null {
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return 'File size exceeds the 10 MB ceiling constraint.'
  }

  const fallbackExtensions = ['.md', '.markdown', '.csv', '.xlsx']
  const hasValidExtension = fallbackExtensions.some((ext) =>
    file.name.toLowerCase().endsWith(ext)
  )
  const isValidType = ALLOWED_MIME_TYPES.includes(file.type) || hasValidExtension

  if (!isValidType) {
    return 'Unsupported format. Please upload PDF, TXT, DOCX, MD, CSV, or XLSX.'
  }

  return null
}