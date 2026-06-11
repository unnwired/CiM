import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import axios from 'axios';

const WatchlistContext = createContext(null);

export function WatchlistProvider({ children, apiBase = '' }) {
  const [watchlists, setWatchlists] = useState([]);
  const [activeWatchlistName, setActiveWatchlistName] = useState(
    () => localStorage.getItem('watchlist.activeName') || '',
  );

  const loadWatchlists = useCallback(async () => {
    try {
      const { data } = await axios.get(`${apiBase}/api/watchlists`);
      setWatchlists(Array.isArray(data?.watchlists) ? data.watchlists : []);
    } catch {
      setWatchlists([]);
    }
  }, [apiBase]);

  const value = useMemo(
    () => ({
      watchlists,
      setWatchlists,
      activeWatchlistName,
      setActiveWatchlistName,
      loadWatchlists,
    }),
    [watchlists, activeWatchlistName, loadWatchlists],
  );

  return <WatchlistContext.Provider value={value}>{children}</WatchlistContext.Provider>;
}

export function useWatchlists() {
  const ctx = useContext(WatchlistContext);
  if (!ctx) throw new Error('useWatchlists must be used within WatchlistProvider');
  return ctx;
}
