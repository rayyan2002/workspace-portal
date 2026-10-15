import { useEffect, useState } from 'react'

/**
 * Delays a value until it stops changing.
 *
 * Used for the search box: with filtering moved to the server, every keystroke would
 * otherwise be a request, and the responses could arrive out of order. The paged hook
 * guards against out-of-order responses too, but not making the requests is better
 * than discarding them.
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
