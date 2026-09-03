import { useEffect, useRef, useState } from 'react';
import { api } from '../api/http';

export function mapHealthToDot(health, fetchOk) {
  if (!fetchOk) return 'red';
  if (health && health.status === 'ok' && (health.db_exists === true || health.db_exists === 1)) {
    return 'green';
  }
  if (health) return 'amber';
  return 'red';
}

export function useServerStatus(enabled) {
  const [healthState, setHealthState] = useState('loading');
  const [usersOnline, setUsersOnline] = useState(null);
  const pollTimerRef = useRef(null);

  useEffect(() => {
    if (!enabled) return undefined;

    let cancelled = false;
    setHealthState('loading');

    async function refreshHealth() {
      try {
        const healthRes = await api.get('/api/health');
        if (cancelled) return;
        const next = mapHealthToDot(
          healthRes.data,
          healthRes.status >= 200 && healthRes.status < 300,
        );
        setHealthState(next);
      } catch (err) {
        if (!cancelled) setHealthState('red');
      }
    }

    async function refreshSocialProof() {
      try {
        const socialRes = await api.get('/api/auth/social-proof');
        if (cancelled) return;
        const n = Number(socialRes.data?.users_online);
        setUsersOnline(Number.isFinite(n) ? n : null);
      } catch {
        if (!cancelled) setUsersOnline(null);
      }
    }

    async function refresh() {
      await Promise.all([refreshHealth(), refreshSocialProof()]);
    }

    function scheduleNext() {
      if (cancelled) return;
      const delayMs = 30000 + Math.random() * 15000;
      pollTimerRef.current = setTimeout(async () => {
        await refresh();
        scheduleNext();
      }, delayMs);
    }

    refresh();
    scheduleNext();

    return () => {
      cancelled = true;
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, [enabled]);

  return { healthState, usersOnline };
}
