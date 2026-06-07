import React, { useState, useEffect, useRef } from 'react';
import { searchStocks } from '../api/client';

export default function SearchBar({ onSearch, onSelectSymbol }) {
  const [query, setQuery]             = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen]               = useState(false);
  const [active, setActive]           = useState(-1);
  const debounceRef                   = useRef(null);
  const inputRef                      = useRef(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setSuggestions([]); setOpen(false); onSearch(''); return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await searchStocks(query);
        setSuggestions(data.results || []);
        setOpen(data.results && data.results.length > 0);
      } catch {
        setSuggestions([]); setOpen(false);
      }
    }, 200);
    onSearch(query);
  }, [query]);

  function handleKeyDown(e) {
    if (!open) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(p => Math.min(p + 1, suggestions.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(p => Math.max(p - 1, 0)); }
    else if (e.key === 'Enter') {
      if (active >= 0 && suggestions[active]) { handleSelect(suggestions[active]); }
    } else if (e.key === 'Escape') { setOpen(false); }
  }

  function handleSelect(symbol) {
    setQuery(''); setSuggestions([]); setOpen(false);
    if (onSelectSymbol) onSelectSymbol(symbol);
  }

  return (
    <div style={{ position: 'relative', flexShrink: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border)',
        borderRadius: 6, padding: '0 10px', height: 32, width: 220,
      }}>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="var(--text-muted)">
          <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z" />
        </svg>
        <input
          ref={inputRef}
          value={query}
          onChange={e => { setQuery(e.target.value); setActive(-1); }}
          onKeyDown={handleKeyDown}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          placeholder="Search symbol..."
          style={{ background: 'transparent', color: 'var(--text-primary)', flex: 1, fontSize: 13 }}
        />
        {query && (
          <button onClick={() => { setQuery(''); setSuggestions([]); setOpen(false); onSearch(''); }}
            style={{ background: 'none', color: 'var(--text-muted)', fontSize: 15, lineHeight: 1 }}>×</button>
        )}
      </div>
      {open && suggestions.length > 0 && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, width: 220,
          backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 6, zIndex: 1000, overflow: 'hidden',
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        }}>
          {suggestions.map((s, i) => (
            <div key={s} onMouseDown={() => handleSelect(s)}
              style={{
                padding: '7px 12px', cursor: 'pointer',
                backgroundColor: i === active ? 'var(--bg-active)' : 'transparent',
                color: i === active ? 'var(--accent-blue)' : 'var(--text-primary)',
                fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 500,
              }}
              onMouseEnter={() => setActive(i)}
            >{s}</div>
          ))}
        </div>
      )}
    </div>
  );
}
