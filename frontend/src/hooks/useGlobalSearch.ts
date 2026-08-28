/**
 * useGlobalSearch — global search Hook
 *
 * wraps global search request logic, debounce 300ms auto search.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { API_PREFIX } from '@/config/app';
import { buildAuthHeaders } from '@/utils/tokenStore';

interface SearchResultItem {
  id: number | string;
  title: string;
  subtitle: string;
  tag?: string;
  tagColor?: string;
  url: string;
  icon?: string;
}

interface SearchResults {
  query: string;
  totalCount: number;
  tasks: SearchResultItem[];
  devices: SearchResultItem[];
  accounts: SearchResultItem[];
  logs: SearchResultItem[];
  settings: SearchResultItem[];
}

export function useGlobalSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResults | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  // H12 fix: keep a ref to the in-flight AbortController so a new search can
  // cancel the previous request. Without this, fast typing produces racing
  // responses and the last-resolved (not last-sent) request wins.
  const abortControllerRef = useRef<AbortController | null>(null);

  const search = useCallback(async (keyword: string) => {
    if (!keyword.trim()) {
      // H12 fix: cancel any in-flight request when clearing.
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      setResults(null);
      setIsLoading(false);
      return;
    }

    // H12 fix: abort previous in-flight request before starting a new one.
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    try {
      // H12 fix: inject Authorization header — previously the request was
      // unauthenticated so the backend 401'd every time and the global
      // search (Ctrl+K) was effectively non-functional.
      // M22: use shared buildAuthHeaders utility.
      const headers = buildAuthHeaders();
      const res = await fetch(`${API_PREFIX}/search/?q=${encodeURIComponent(keyword)}&page_size=5`, {
        headers,
        signal: controller.signal,
      });
      if (res.ok) {
        const data = await res.json();
        // Guard against out-of-order responses: only commit if this request
        // is still the latest one.
        if (abortControllerRef.current === controller) {
          setResults(data);
        }
      } else {
        if (abortControllerRef.current === controller) {
          setResults(null);
        }
      }
    } catch (err) {
      // AbortError is expected when a newer search supersedes this one.
      if ((err as Error).name !== 'AbortError' && abortControllerRef.current === controller) {
        setResults(null);
      }
    } finally {
      if (abortControllerRef.current === controller) {
        setIsLoading(false);
        abortControllerRef.current = null;
      }
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => search(query), 300);
    return () => clearTimeout(timer);
  }, [query, search]);

  // H12 fix: abort any in-flight request on unmount.
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, []);

  return { query, setQuery, results: results as SearchResults | null, isLoading };
}

export type { SearchResultItem, SearchResults };

export default useGlobalSearch;
