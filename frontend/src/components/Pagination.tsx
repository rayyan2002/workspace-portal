import { ChevronLeft, ChevronRight } from 'lucide-react'

interface PaginationProps {
  page: number
  totalPages: number
  total: number
  size: number
  onChange: (page: number) => void
  /** What is being counted, e.g. "documents". Shown in the range label. */
  label: string
}

/**
 * Page navigation for a list.
 *
 * <p>Shows the range and total ("21–40 of 250") rather than page numbers alone,
 * because "page 2 of 13" tells a user nothing about how much there is. The total is
 * the field the envelope exists to carry.
 */
export default function Pagination({ page, totalPages, total, size, onChange, label }: PaginationProps) {
  if (total === 0) return null

  const first = page * size + 1
  const last = Math.min((page + 1) * size, total)

  return (
    <nav className="pagination" aria-label={`${label} pagination`}>
      <p className="pagination-range" aria-live="polite">
        {first}–{last} of {total} {label}
      </p>

      <div className="pagination-controls">
        <button
          type="button"
          className="pagination-btn"
          onClick={() => onChange(page - 1)}
          disabled={page === 0}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
          <span>Previous</span>
        </button>

        <span className="pagination-position">Page {page + 1} of {totalPages}</span>

        <button
          type="button"
          className="pagination-btn"
          onClick={() => onChange(page + 1)}
          disabled={page >= totalPages - 1}
          aria-label="Next page"
        >
          <span>Next</span>
          <ChevronRight size={16} />
        </button>
      </div>
    </nav>
  )
}
