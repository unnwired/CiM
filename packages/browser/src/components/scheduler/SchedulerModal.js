import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import useAdminJobStatus from '../../hooks/useAdminJobStatus';
import EnabledSchedulersList from './EnabledSchedulersList';
import SchedulerLogPanel from './SchedulerLogPanel';
import SchedulerTaskEditor from './SchedulerTaskEditor';
import { activeSchedulesViewportStyle } from './schedulerFieldStyles';
import {
  buildConfigFromForm,
  defaultForm,
  formFromConfig,
  SCHEDULER_TASKS,
} from './schedulerTasks';

const API = '';

export default function SchedulerModal({
  open,
  onClose,
  canEdit = true,
  showOperatorHint = false,
}) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');
  const [serverStatus, setServerStatus] = useState(null);
  const [watchdogStatus, setWatchdogStatus] = useState(null);
  const [form, setForm] = useState(defaultForm);
  const [selectedKey, setSelectedKey] = useState(SCHEDULER_TASKS[0].key);
  const dirtyRef = useRef(false);
  const saveTimerRef = useRef(null);

  const { status: jobStatus, startPolling } = useAdminJobStatus({ autoStart: false });
  const isRunning = !!jobStatus?.running;

  const applyStatus = useCallback((data, syncForm = false) => {
    setServerStatus(data || null);
    if (syncForm && data?.config) {
      setForm(formFromConfig(data.config));
      dirtyRef.current = false;
    }
  }, []);

  const fetchStatus = useCallback(async (syncForm = false) => {
    if (!open) return;
    try {
      const schedulesRes = await axios.get(`${API}/api/admin/schedules`);
      applyStatus(schedulesRes.data, syncForm && !dirtyRef.current);
      if (canEdit) {
        try {
          const watchdogRes = await axios.get(`${API}/api/admin/live-watchdog-status`);
          setWatchdogStatus(watchdogRes.data);
        } catch {
          setWatchdogStatus(null);
        }
      }
    } catch (e) {
      if (syncForm) {
        setMsg(e.response?.data?.detail || e.message || 'Failed to load schedule');
      }
    }
  }, [open, applyStatus, canEdit]);

  useEffect(() => {
    if (!open) return undefined;
    setLoading(true);
    setMsg('');
    fetchStatus(true).finally(() => setLoading(false));
    const id = window.setInterval(() => fetchStatus(false), 10000);
    return () => window.clearInterval(id);
  }, [open, fetchStatus]);

  const persistForm = useCallback(async (nextForm, quiet = false) => {
    if (!canEdit) return;
    if (!quiet) setSaving(true);
    if (!quiet) setMsg('');
    try {
      const r = await axios.put(`${API}/api/admin/schedules`, buildConfigFromForm(nextForm));
      applyStatus(r.data, !quiet);
      if (!quiet) setMsg('Schedule saved.');
    } catch (e) {
      setMsg(e.response?.data?.detail || e.message || 'Save failed');
    } finally {
      if (!quiet) setSaving(false);
    }
  }, [canEdit, applyStatus]);

  const scheduleSave = useCallback((nextForm) => {
    dirtyRef.current = true;
    setForm(nextForm);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      persistForm(nextForm, true);
      dirtyRef.current = false;
    }, 300);
  }, [persistForm]);

  useEffect(() => () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
  }, []);

  function patchTask(key, patch) {
    if (!canEdit) return;
    scheduleSave({ ...form, [key]: { ...(form[key] || {}), ...patch } });
  }

  async function enableTask(key) {
    if (!canEdit) return;
    const next = {
      ...form,
      [key]: { ...(form[key] || {}), enabled: true },
    };
    dirtyRef.current = true;
    setForm(next);
    await persistForm(next, false);
    setMsg(`Enabled: ${SCHEDULER_TASKS.find((t) => t.key === key)?.label || key}`);
  }

  async function removeTask(key) {
    if (!canEdit) return;
    const next = {
      ...form,
      [key]: { ...(form[key] || {}), enabled: false },
    };
    dirtyRef.current = true;
    setForm(next);
    await persistForm(next, false);
  }

  async function runTask(taskKey) {
    if (!canEdit) return;
    setMsg('');
    try {
      await axios.post(`${API}/api/admin/schedules/run-now`, { task: taskKey });
      setMsg(`Started: ${taskKey}`);
      startPolling();
      fetchStatus(false);
    } catch (e) {
      setMsg(e.response?.data?.detail || e.message || 'Failed to start job');
    }
  }

  if (!open) return null;

  const config = serverStatus?.config || buildConfigFromForm(form);
  const activeScheduleCount = SCHEDULER_TASKS.filter((t) => config[t.key]?.enabled).length;
  const port = typeof window !== 'undefined' && window.location.port ? window.location.port : '8002';

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.6)',
        zIndex: 9000,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: 16,
        paddingBottom: 16,
        overflowY: 'auto',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        width: 540,
        maxWidth: '96vw',
        maxHeight: 'calc(100vh - 32px)',
        overflow: 'hidden',
        boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
      }}
      >
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--bg-tertiary)',
          flexShrink: 0,
        }}
        >
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Admin Scheduler</span>
          <button
            type="button"
            aria-label="Close scheduler"
            onClick={onClose}
            style={{ background: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        <div style={{
          padding: '10px 14px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          overflowY: 'auto',
          overflowX: 'hidden',
          flex: '1 1 auto',
          minHeight: 0,
        }}
        >
          {showOperatorHint && !canEdit && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', backgroundColor: 'rgba(56,139,253,0.08)', border: '1px solid rgba(56,139,253,0.35)', borderRadius: 6, padding: '10px 12px' }}>
              Sign in as operator via <code style={{ fontSize: 11 }}>Admin-Showcase.bat</code> or{' '}
              <code style={{ fontSize: 11 }}>{`http://127.0.0.1:${port}/?operator=1`}</code>.
            </div>
          )}

          {canEdit && watchdogStatus?.available && watchdogStatus.overallOk === false && (
            <div style={{
              fontSize: 12,
              color: 'var(--accent-red)',
              backgroundColor: 'rgba(248,81,73,0.1)',
              border: '1px solid rgba(248,81,73,0.45)',
              borderRadius: 6,
              padding: '10px 12px',
              lineHeight: 1.4,
            }}
            >
              <strong>Live client link unhealthy</strong>
              {' — '}
              web {watchdogStatus.webPublicOk ? 'OK' : 'down'}
              {', '}
              mobile {watchdogStatus.mobilePublicOk ? 'OK' : 'down'}
              {watchdogStatus.lastCheckAt && (
                <span style={{ color: 'var(--text-muted)' }}>
                  {` · last check ${watchdogStatus.lastCheckAt}`}
                </span>
              )}
              {watchdogStatus.lastHealAction && (
                <span style={{ color: 'var(--text-muted)' }}>
                  {` · heal: ${watchdogStatus.lastHealAction}`}
                </span>
              )}
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                See runtime/logs/live-watchdog.log on the host PC. Re-run Start-Live-WebAndMobile.bat if needed.
              </div>
            </div>
          )}

          {canEdit && watchdogStatus?.available === false && watchdogStatus?.message && (
            <div style={{
              fontSize: 11,
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-tertiary)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '8px 10px',
            }}
            >
              {watchdogStatus.message}
            </div>
          )}

          <SchedulerLogPanel logTail={serverStatus?.logTail} />

          <div style={{
            padding: '6px 10px',
            borderRadius: 6,
            border: `1px solid ${isRunning ? 'rgba(248,81,73,0.45)' : 'var(--border)'}`,
            backgroundColor: isRunning ? 'rgba(248,81,73,0.06)' : 'var(--bg-tertiary)',
            flexShrink: 0,
          }}
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
              marginBottom: 4,
            }}
            >
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
                Current activity
              </div>
              {saving && (
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Saving…</div>
              )}
            </div>
            {isRunning ? (
              <div style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.35 }}>
                <strong>{jobStatus?.job || 'job'}</strong>
                {' — '}
                {jobStatus?.message || 'Running…'}
                {jobStatus?.total > 0 && (
                  <span style={{ color: 'var(--text-muted)' }}> ({Math.round(jobStatus.percent || 0)}%)</span>
                )}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                Scheduler idle
                {serverStatus?.waitingTask && (
                  <span style={{ color: 'var(--text-muted)' }}>
                    {' · Waiting: '}
                    {serverStatus.waitingTask}
                  </span>
                )}
              </div>
            )}
          </div>

          <div style={{ flexShrink: 0 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: 6 }}>Active schedules</div>
            <div style={activeSchedulesViewportStyle(activeScheduleCount)}>
              {loading && !serverStatus ? (
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading…</div>
              ) : (
                <EnabledSchedulersList
                  config={config}
                  nextRuns={serverStatus?.nextRuns || {}}
                  state={serverStatus?.state || {}}
                  canEdit={canEdit}
                  jobRunning={isRunning}
                  onRemove={removeTask}
                  onRunNow={runTask}
                />
              )}
            </div>
          </div>

          <SchedulerTaskEditor
            selectedKey={selectedKey}
            onSelectKey={setSelectedKey}
            draft={form}
            onPatch={patchTask}
            canEdit={canEdit}
            jobRunning={isRunning}
            onEnable={enableTask}
            onRunNow={runTask}
          />

          {msg && (
            <div style={{
              fontSize: 11,
              color: /fail|error|404|not available|already running/i.test(msg) ? 'var(--accent-red)' : 'var(--accent-green)',
              backgroundColor: /fail|error|404|not available|already running/i.test(msg) ? 'rgba(248,81,73,0.1)' : 'rgba(63,185,80,0.1)',
              border: `1px solid ${/fail|error|404|not available|already running/i.test(msg) ? 'var(--accent-red)' : 'var(--accent-green)'}`,
              borderRadius: 5,
              padding: '6px 10px',
              flexShrink: 0,
            }}
            >
              {msg}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
