import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/client'
import type { PageResponse } from '../Type'

interface PagedState<T> {
  items: T[]
  total: number
  page: number
  size: number
  loading: boolean
  error: string | null
}

/**
 * Fetches one page of a list endpoint.
 *
 * <p>Kept separate from `useFetch` rather than teaching that hook to unwrap an
 * envelope. Silently returning `.items` would work, but it would also throw away
 * `total` — and `total` is the whole reason the envelope exists, since without it a
 * pager cannot know how many pages there are. A hook that quietly discards the useful
 * half of a response is worse than a second hook.
 */
export function usePagedFetch<T>(path: string, size = 20) {
  const [state, setState] = useState<PagedState<T>>({
    items: [], total: 0, page: 0, size, loading: true, error: null,
  })

  const [page, setPage] = useState(0)
  const [reloadToken, setReloadToken] = useState(0)

  // Guards against a slow first page resolving after a fast second one and
  // overwriting it — the classic out-of-order response bug in paged lists.
  const requestSeq = useRef(0)

  useEffect(() => {
    const seq = ++requestSeq.current
    let cancelled = false

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }))
      try {
        const separator = path.includes('?') ? '&' : '?'
        const response = await apiFetch(`${path}${separator}page=${page}&size=${size}`)
        if (!response.ok) throw new Error('Failed to load this page.')

        const body = (await response.json()) as PageResponse<T>
        if (cancelled || seq !== requestSeq.current) return

        setState({
          items: body.items, total: body.total, page: body.page, size: body.size,
          loading: false, error: null,
        })
      } catch (err) {
        if (cancelled || seq !== requestSeq.current) return
        setState((prev) => ({
          ...prev, loading: false,
          error: err instanceof Error ? err.message : 'Failed to load this page.',
        }))
      }
    }

    load()
    return () => { cancelled = true }
  }, [path, page, size, reloadToken])

  const refetch = useCallback(() => setReloadToken((t) => t + 1), [])

  const totalPages = Math.max(1, Math.ceil(state.total / (state.size || 1)))

  return {
    ...state,
    totalPages,
    goToPage: (next: number) => setPage(Math.max(0, Math.min(next, totalPages - 1))),
    refetch,
    /**
     * Local edit to the current page — an optimistic delete, or an upload prepended.
     *
     * The total is adjusted by the LENGTH DELTA rather than assumed to be a deletion.
     * The first version decremented unconditionally, which made an upload decrease the
     * reported count.
     */
    setItems: (updater: (previous: T[]) => T[]) =>
      setState((prev) => {
        const items = updater(prev.items)
        return { ...prev, items, total: Math.max(0, prev.total + (items.length - prev.items.length)) }
      }),
  }
}
