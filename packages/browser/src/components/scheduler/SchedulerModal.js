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
  filterScheduleFromEntry,
  FILTER_REBUILD_KEY,
  filterSelectionId,
  formFromConfig,
  isFilterRebuildKey,
  isTaskScheduleKey,
  newFilterSchedule,
  newTaskSchedule,
  taskMeta,
  taskScheduleFromEntry,
  taskSelectionId,
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
  const [filterSchedules, setFilterSchedules] = useState([]);
  const [taskSchedules, setTaskSchedules] = useState([]);
  const [filterDraft, setFilterDraft] = useState(() => newFilterSchedule());
  const [taskDraft, setTaskDraft] = useState(() => newTaskSchedule('ohlcv'));
  const [filterOptions, setFilterOptions] = useState(null);
  const [selectedKey, setSelectedKey] = useState(FILTER_REBUILD_KEY);
  const dirtyRef = useRef(false);
  const saveTimerRef = useRef(null);
  const formRef = useRef(form);
  const filterSchedulesRef = useRef(filterSchedules);
  const taskSchedulesRef = useRef(taskSchedules);

  const setFormSynced = useCallback((next) => {
    formRef.current = next;
    setForm(next);
  }, []);
  const setFilterSchedulesSynced = useCallback((next) => {
    filterSchedulesRef.current = next;
    setFilterSchedules(next);
  }, []);
  const setTaskSchedulesSynced = useCallback((next) => {
    taskSchedulesRef.current = next;
    setTaskSchedules(next);
  }, []);

  const { status: jobStatus, startPolling } = useAdminJobStatus({ autoStart: false });
  const isRunning = !!jobStatus?.running;

  const applyStatus = useCallback((data, syncForm = false) => {
    setServerStatus(data || null);
    if (syncForm && data?.config) {
      setFormSynced(formFromConfig(data.config));
      const schedules = Array.isArray(data.config.filterSchedules) ? data.config.filterSchedules : [];
      setFilterSchedulesSynced(schedules);
      const tasks = Array.isArray(data.config.taskSchedules) ? data.config.taskSchedules : [];
      setTaskSchedulesSynced(tasks);
      dirtyRef.current = false;
    }
  }, [setFormSynced, setFilterSchedulesSynced, setTaskSchedulesSynced]);

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

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    axios.get(`${API}/api/admin/filter-rebuild/options`)
      .then((r) => { if (!cancelled) setFilterOptions(r.data); })
      .catch(() => { if (!cancelled) setFilterOptions(null); });
    return () => { cancelled = true; };
  }, [open]);

  const persistConfig = useCallback(async (nextForm, nextFilterSchedules, nextTaskSchedules, quiet = false) => {
    if (!canEdit) return;
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (!quiet) setSaving(true);
    if (!quiet) setMsg('');
    try {
      const payload = buildConfigFromForm(nextForm, nextFilterSchedules, nextTaskSchedules);
      const r = await axios.put(`${API}/api/admin/schedules`, payload);
      applyStatus(r.data, !quiet);
      dirtyRef.current = false;
      if (!quiet) setMsg('Schedule saved.');
    } catch (e) {
      setMsg(e.response?.data?.detail || e.message || 'Save failed');
    } finally {
      if (!quiet) setSaving(false);
    }
  }, [canEdit, applyStatus]);

  useEffect(() => () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
  }, []);

  function patchTaskDraft(patch) {
    if (!canEdit) return;
    dirtyRef.current = true;
    setTaskDraft((prev) => ({ ...prev, ...patch }));
  }

  function patchFilterDraft(patch) {
    if (!canEdit) return;
    dirtyRef.current = true;
    setFilterDraft((prev) => {
      const nextDraft = { ...prev, ...patch };
      if (patch.preset) {
        nextDraft.preset = { ...(prev.preset || {}), ...patch.preset };
      }
      return nextDraft;
    });
  }

  function beginCreateDraft(taskKey = FILTER_REBUILD_KEY) {
    dirtyRef.current = false;
    if (taskKey === FILTER_REBUILD_KEY || isFilterRebuildKey(taskKey)) {
      setFilterDraft(newFilterSchedule());
      setSelectedKey(FILTER_REBUILD_KEY);
      return;
    }
    setTaskDraft(newTaskSchedule(taskKey));
    setSelectedKey(taskKey);
  }

  function selectEditor(key) {
    setSelectedKey(key);
    if (isFilterRebuildKey(key)) {
      const id = filterSelectionId(key);
      if (id) {
        const source = serverStatus?.config?.filterSchedules || filterSchedules;
        const entry = source.find((s) => s.id === id)
          || filterSchedules.find((s) => s.id === id);
        if (entry) {
          setFilterDraft(filterScheduleFromEntry(entry));
          dirtyRef.current = false;
        }
      } else {
        setFilterDraft(newFilterSchedule());
        dirtyRef.current = false;
      }
      return;
    }
    if (isTaskScheduleKey(key)) {
      const id = taskSelectionId(key);
      const source = serverStatus?.config?.taskSchedules || taskSchedules;
      const entry = source.find((s) => s.id === id)
        || taskSchedules.find((s) => s.id === id);
      if (entry) {
        setTaskDraft(taskScheduleFromEntry(entry));
        dirtyRef.current = false;
      }
    }
  }

  async function createSchedule() {
    if (!canEdit) return;
    if (isFilterRebuildKey(selectedKey) || selectedKey === FILTER_REBUILD_KEY) {
      const draft = { ...filterDraft, enabled: true };
      const current = filterSchedulesRef.current.filter((s) => s.id !== draft.id);
      const nextSchedules = [...current, draft];
      dirtyRef.current = true;
      setFilterSchedulesSynced(nextSchedules);
      await persistConfig(formRef.current, nextSchedules, taskSchedulesRef.current, false);
      setMsg('Created: Filter rebuild schedule');
      setFilterDraft(newFilterSchedule());
      setSelectedKey(FILTER_REBUILD_KEY);
      return;
    }
    const draft = { ...taskDraft, enabled: true };
    const current = taskSchedulesRef.current.filter((s) => s.id !== draft.id);
    const nextTasks = [...current, draft];
    dirtyRef.current = true;
    setTaskSchedulesSynced(nextTasks);
    await persistConfig(formRef.current, filterSchedulesRef.current, nextTasks, false);
    const label = taskMeta(draft.taskKey)?.label || draft.taskKey;
    setMsg(`Created: ${label}`);
    setTaskDraft(newTaskSchedule(draft.taskKey));
    setSelectedKey(draft.taskKey);
  }

  async function saveScheduleEdits() {
    if (!canEdit) return;
    if (isFilterRebuildKey(selectedKey)) {
      const id = filterSelectionId(selectedKey) || filterDraft?.id;
      if (!id) return;
      const draft = { ...filterDraft, id };
      const nextSchedules = filterSchedulesRef.current.map((s) => (s.id === id ? { ...s, ...draft, preset: draft.preset } : s));
      if (!nextSchedules.some((s) => s.id === id)) {
        nextSchedules.push({ ...draft, enabled: true });
      }
      dirtyRef.current = true;
      setFilterSchedulesSynced(nextSchedules);
      await persistConfig(formRef.current, nextSchedules, taskSchedulesRef.current, false);
      setMsg('Saved: Filter rebuild schedule');
      return;
    }
    const id = taskSelectionId(selectedKey) || taskDraft?.id;
    if (!id) return;
    const draft = { ...taskDraft, id };
    const nextTasks = taskSchedulesRef.current.map((s) => (s.id === id ? { ...s, ...draft } : s));
    if (!nextTasks.some((s) => s.id === id)) {
      nextTasks.push({ ...draft, enabled: true });
    }
    dirtyRef.current = true;
    setTaskSchedulesSynced(nextTasks);
    await persistConfig(formRef.current, filterSchedulesRef.current, nextTasks, false);
    setMsg(`Saved: ${taskMeta(draft.taskKey)?.label || draft.taskKey}`);
  }

  function cancelEditor() {
    dirtyRef.current = false;
    const filterId = filterSelectionId(selectedKey);
    if (filterId) {
      const source = serverStatus?.config?.filterSchedules || filterSchedulesRef.current;
      const entry = source.find((s) => s.id === filterId);
      if (entry) setFilterDraft(filterScheduleFromEntry(entry));
      else {
        setFilterDraft(newFilterSchedule());
        setSelectedKey(FILTER_REBUILD_KEY);
      }
      return;
    }
    const taskId = taskSelectionId(selectedKey);
    if (taskId) {
      const source = serverStatus?.config?.taskSchedules || taskSchedulesRef.current;
      const entry = source.find((s) => s.id === taskId);
      if (entry) setTaskDraft(taskScheduleFromEntry(entry));
      else {
        setTaskDraft(newTaskSchedule('ohlcv'));
        setSelectedKey(FILTER_REBUILD_KEY);
      }
      return;
    }
    setFilterDraft(newFilterSchedule());
    setTaskDraft(newTaskSchedule('ohlcv'));
    setSelectedKey(FILTER_REBUILD_KEY);
    setMsg('');
  }

  async function setTaskEnabled(id, enabled) {
    if (!canEdit) return;
    const nextTasks = taskSchedulesRef.current.map((s) => (
      s.id === id ? { ...s, enabled: !!enabled } : s
    ));
    dirtyRef.current = true;
    setTaskSchedulesSynced(nextTasks);
    await persistConfig(formRef.current, filterSchedulesRef.current, nextTasks, false);
  }

  async function deleteTaskSchedule(id) {
    if (!canEdit) return;
    const nextTasks = taskSchedulesRef.current.filter((s) => s.id !== id);
    dirtyRef.current = true;
    setTaskSchedulesSynced(nextTasks);
    if (taskSelectionId(selectedKey) === id) {
      const removed = taskSchedulesRef.current.find((s) => s.id === id);
      beginCreateDraft(removed?.taskKey || 'ohlcv');
    }
    await persistConfig(formRef.current, filterSchedulesRef.current, nextTasks, false);
  }

  async function setFilterEnabled(id, enabled) {
    if (!canEdit) return;
    const nextSchedules = filterSchedulesRef.current.map((s) => (
      s.id === id ? { ...s, enabled: !!enabled } : s
    ));
    dirtyRef.current = true;
    setFilterSchedulesSynced(nextSchedules);
    await persistConfig(formRef.current, nextSchedules, taskSchedulesRef.current, false);
  }

  async function deleteFilterSchedule(id) {
    if (!canEdit) return;
    const nextSchedules = filterSchedulesRef.current.filter((s) => s.id !== id);
    dirtyRef.current = true;
    setFilterSchedulesSynced(nextSchedules);
    if (filterSelectionId(selectedKey) === id) {
      setSelectedKey(FILTER_REBUILD_KEY);
      setFilterDraft(newFilterSchedule());
    }
    await persistConfig(formRef.current, nextSchedules, taskSchedulesRef.current, false);
  }

  async function runTask(taskKey) {
    if (!canEdit) return;
    setMsg('');
    try {
      const r = await axios.post(`${API}/api/admin/schedules/run-now`, { task: taskKey });
      const data = r?.data || {};
      if (data.queued) {
        setMsg(`Queued: ${taskKey} (will run after the current job)`);
      } else if (data.ok === false) {
        setMsg(data.error || `Failed: ${taskKey}`);
      } else {
        setMsg(`Started: ${taskKey}`);
      }
      startPolling();
      fetchStatus(false);
    } catch (e) {
      setMsg(e.response?.data?.detail || e.message || 'Failed to start job');
    }
  }

  if (!open) return null;

  const config = serverStatus?.config || buildConfigFromForm(form, filterSchedules, taskSchedules);
  const displayFilterSchedules = serverStatus?.config?.filterSchedules || filterSchedules;
  const displayTaskSchedules = serverStatus?.config?.taskSchedules || taskSchedules;
  const activeScheduleCount = displayTaskSchedules.length + displayFilterSchedules.length;
  const port = typeof window !== 'undefined' && window.location.port ? window.location.port : '8002';
  const editingFilterId = filterSelectionId(selectedKey);
  const editingTaskId = taskSelectionId(selectedKey);
  const isCreateMode = isFilterRebuildKey(selectedKey)
    ? !editingFilterId
    : !editingTaskId;
  const editorSelectedKey = isFilterRebuildKey(selectedKey)
    ? (editingFilterId ? selectedKey : FILTER_REBUILD_KEY)
    : (editingTaskId ? selectedKey : (taskDraft.taskKey || 'ohlcv'));

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

          {canEdit && watchdogStatus?.available && watchdogStatus.overallOk === false && !watchdogStatus.stale && (
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
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
              paddingTop: 4,
              paddingBottom: 8,
              marginBottom: 2,
            }}
            >
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
                Active schedules
              </div>
              {canEdit && (
                <button
                  type="button"
                  onClick={() => beginCreateDraft(FILTER_REBUILD_KEY)}
                  style={{
                    border: '1px solid var(--border)',
                    borderRadius: 5,
                    padding: '6px 12px',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: 'pointer',
                    backgroundColor: 'var(--bg-primary)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  + New Schedule
                </button>
              )}
            </div>
            <div style={activeSchedulesViewportStyle(activeScheduleCount)}>
              {loading && !serverStatus ? (
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading…</div>
              ) : (
                <EnabledSchedulersList
                  config={config}
                  taskSchedules={displayTaskSchedules}
                  filterSchedules={displayFilterSchedules}
                  filterOptions={filterOptions}
                  nextRuns={serverStatus?.nextRuns || {}}
                  state={serverStatus?.state || {}}
                  canEdit={canEdit}
                  jobRunning={isRunning}
                  onEnableTask={(id) => setTaskEnabled(id, true)}
                  onDisableTask={(id) => setTaskEnabled(id, false)}
                  onDeleteTask={deleteTaskSchedule}
                  onEnableFilter={(id) => setFilterEnabled(id, true)}
                  onDisableFilter={(id) => setFilterEnabled(id, false)}
                  onDeleteFilter={deleteFilterSchedule}
                  onRunNow={runTask}
                  onEdit={selectEditor}
                  selectedKey={selectedKey}
                />
              )}
            </div>
          </div>

          <SchedulerTaskEditor
            selectedKey={editorSelectedKey}
            onSelectKey={(key) => {
              if (isFilterRebuildKey(key) || key === FILTER_REBUILD_KEY) {
                beginCreateDraft(FILTER_REBUILD_KEY);
                return;
              }
              // Always create a new instance of that task type (multi-schedule).
              beginCreateDraft(key);
            }}
            taskDraft={taskDraft}
            filterDraft={filterDraft}
            onPatchTask={patchTaskDraft}
            onPatchFilter={patchFilterDraft}
            canEdit={canEdit}
            isCreateMode={isCreateMode}
            onCreate={createSchedule}
            onSave={saveScheduleEdits}
            onCancel={cancelEditor}
          />

          {msg && (
            <div style={{
              fontSize: 11,
              color: /fail|error|404|not available/i.test(msg) && !/queued/i.test(msg) ? 'var(--accent-red)' : 'var(--accent-green)',
              backgroundColor: /fail|error|404|not available/i.test(msg) && !/queued/i.test(msg) ? 'rgba(248,81,73,0.1)' : 'rgba(63,185,80,0.1)',
              border: `1px solid ${/fail|error|404|not available/i.test(msg) && !/queued/i.test(msg) ? 'var(--accent-red)' : 'var(--accent-green)'}`,
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
