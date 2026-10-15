import { useState, useEffect, useCallback } from 'react'
import type { DependencyList } from 'react' 
import { apiFetch } from '../api/client' // <-- ADDED: Import our new adapter

interface FetchOptions {
  skip?: boolean
  deps?: DependencyList
}

export function useFetch<T>(url: string, options: FetchOptions = {}) {
  const { skip = false, deps = [] } = options

  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState<boolean>(!skip)
  const [error, setError] = useState<string | null>(null)

  const fetchInternal = useCallback(async (ignoreFlag?: { current: boolean }) => {
    try {
      // <-- FIXED: Swapped native fetch for apiFetch to hit Spring Boot with auth headers
      const response = await apiFetch(url) 
      
      if (!response.ok) {
        let errorMessage = 'An unexpected error occurred.'
        try {
          // Attempt to parse structured APIError body
          const errData = await response.json()
          if (errData && errData.message) {
            errorMessage = errData.message
          } else {
            errorMessage = `Error ${response.status}: ${response.statusText}`
          }
        } catch { 
          // Fallback if the body is empty or not JSON
          errorMessage = `Error ${response.status}: ${response.statusText}`
        }
        throw new Error(errorMessage)
      }
      
      const jsonData = await response.json()
      
      if (!ignoreFlag || !ignoreFlag.current) {
        setData(jsonData)
        setError(null)
      }
    } catch (err) {
      if (!ignoreFlag || !ignoreFlag.current) {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      if (!ignoreFlag || !ignoreFlag.current) {
        setLoading(false)
      }
    }
  }, [url])

  useEffect(() => {
    if (skip) {
      setLoading(false)
      return
    }

    setLoading(true)
    const ignoreObj = { current: false }
    
    fetchInternal(ignoreObj)

    return () => {
      // The race-condition killer
      ignoreObj.current = true
    }
    
    // Note: React requires the dependency array to have a constant length between renders.
    // Callers MUST ensure `deps` is a fixed-length array to prevent React from throwing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, skip, ...(deps || [])])

  const refetch = useCallback(async () => {
    setLoading(true)
    await fetchInternal()
  }, [fetchInternal])

  return { data, loading, error, refetch, setData }
}