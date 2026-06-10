import React, { useCallback, useEffect, useState } from 'react';
import { fetchKnowledgeBasePage, saveKnowledgeBasePage } from '../api/knowledgeBase';
import {
  KNOWLEDGE_BASE_PAGE_GROUPS,
  KNOWLEDGE_BASE_PAGES,
} from '../content/knowledgeBasePages';

const inp = {
  width: '100%',
  padding: '6px 8px',
  fontSize: 12,
  borderRadius: 4,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-tertiary)',
  color: 'var(--text-primary)',
  boxSizing: 'border-box',
};

const lbl = {
  display: 'block',
  fontSize: 11,
  color: 'var(--text-secondary)',
  marginBottom: 4,
};

function emptySection() {
  return { heading: 'New section', paragraphs: [''] };
}

function paragraphsToText(paragraphs) {
  return (paragraphs || []).join('\n\n');
}

function textToParagraphs(text) {
  return String(text || '')
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export default function KnowledgeBaseEditor({
  onClose,
  initialGuideId = 'dashboard',
  onSaved,
  onPreview,
}) {
  const [guideId, setGuideId] = useState(initialGuideId);
  const [title, setTitle] = useState('');
  const [sections, setSections] = useState([emptySection()]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const loadPage = useCallback(async (id) => {
    setLoading(true);
    setMessage('');
    try {
      const page = await fetchKnowledgeBasePage(id);
      setTitle(page?.title || '');
      const secs = Array.isArray(page?.sections) && page.sections.length
        ? page.sections.map((s) => ({
          heading: s.heading || '',
          paragraphs: Array.isArray(s.paragraphs) && s.paragraphs.length ? s.paragraphs : [''],
        }))
        : [emptySection()];
      setSections(secs);
    } catch (e) {
      setMessage(e.response?.data?.detail || e.message || 'Failed to load page.');
      setTitle('');
      setSections([emptySection()]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPage(guideId);
  }, [guideId, loadPage]);

  function updateSection(idx, patch) {
    setSections((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }

  function addSection() {
    setSections((prev) => [...prev, emptySection()]);
  }

  function removeSection(idx) {
    setSections((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));
  }

  function buildPayload() {
    return {
      title: title.trim(),
      sections: sections
        .map((s) => ({
          heading: String(s.heading || '').trim(),
          paragraphs: (Array.isArray(s.paragraphs) ? s.paragraphs : [])
            .map((p) => String(p || '').trim())
            .filter(Boolean),
        }))
        .filter((s) => s.heading && s.paragraphs.length),
    };
  }

  async function handleSave() {
    const payload = buildPayload();
    if (!payload.title || !payload.sections.length) {
      setMessage('Title and at least one section with content are required.');
      return;
    }
    setSaving(true);
    setMessage('');
    try {
      await saveKnowledgeBasePage(guideId, payload);
      setMessage('Saved.');
      onSaved && onSaved(guideId);
    } catch (e) {
      setMessage(e.response?.data?.detail || e.message || 'Save failed.');
    } finally {
      setSaving(false);
    }
  }

  function handlePreview() {
    const payload = buildPayload();
    if (!payload.title || !payload.sections.length) {
      setMessage('Add a title and section content before previewing.');
      return;
    }
    onPreview && onPreview(guideId, payload);
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.6)',
        zIndex: 9000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          width: 'min(720px, 100%)',
          maxHeight: 'min(88vh, 900px)',
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          boxShadow: '0 12px 40px rgba(0,0,0,0.55)',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            Edit Knowledge Base
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close Knowledge Base editor"
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1, cursor: 'pointer' }}
          >
            ×
          </button>
        </div>

        <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>
          <label style={lbl}>
            Page
            <select
              value={guideId}
              onChange={(e) => setGuideId(e.target.value)}
              style={{ ...inp, marginTop: 4 }}
            >
              {KNOWLEDGE_BASE_PAGE_GROUPS.map((group) => {
                const pages = KNOWLEDGE_BASE_PAGES.filter((p) => p.group === group.key);
                if (!pages.length) return null;
                return (
                  <optgroup key={group.key} label={group.label}>
                    {pages.map((p) => (
                      <option key={p.id} value={p.id}>{p.label}</option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
          </label>

          {loading ? (
            <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-secondary)' }}>Loading…</div>
          ) : (
            <>
              <label style={{ ...lbl, marginTop: 14 }}>
                Title
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  style={{ ...inp, marginTop: 4 }}
                />
              </label>

              <div style={{ marginTop: 16, fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                Sections
              </div>

              {sections.map((section, idx) => (
                <div
                  key={`section-${idx}`}
                  style={{
                    marginTop: 12,
                    padding: 12,
                    border: '1px solid var(--border-light)',
                    borderRadius: 6,
                    backgroundColor: 'var(--bg-primary)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      Section
                      {' '}
                      {idx + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeSection(idx)}
                      disabled={sections.length <= 1}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: sections.length <= 1 ? 'var(--text-muted)' : '#f85149',
                        fontSize: 11,
                        cursor: sections.length <= 1 ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Remove
                    </button>
                  </div>
                  <label style={lbl}>
                    Heading
                    <input
                      type="text"
                      value={section.heading}
                      onChange={(e) => updateSection(idx, { heading: e.target.value })}
                      style={{ ...inp, marginTop: 4 }}
                    />
                  </label>
                  <label style={{ ...lbl, marginTop: 10 }}>
                    Paragraphs (blank line between paragraphs)
                    <textarea
                      value={paragraphsToText(section.paragraphs)}
                      onChange={(e) => updateSection(idx, { paragraphs: textToParagraphs(e.target.value) })}
                      rows={5}
                      style={{ ...inp, marginTop: 4, resize: 'vertical', fontFamily: 'inherit' }}
                    />
                  </label>
                </div>
              ))}

              <button
                type="button"
                onClick={addSection}
                style={{
                  marginTop: 12,
                  padding: '6px 10px',
                  fontSize: 12,
                  borderRadius: 4,
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-tertiary)',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                }}
              >
                + Add section
              </button>
            </>
          )}

          {message && (
            <div style={{ marginTop: 14, fontSize: 12, color: message === 'Saved.' ? '#3fb950' : '#f85149' }}>
              {message}
            </div>
          )}
        </div>

        <div style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 8,
          padding: '12px 16px',
          borderTop: '1px solid var(--border)',
          flexShrink: 0,
        }}
        >
          <button
            type="button"
            onClick={handlePreview}
            disabled={loading || saving}
            style={{
              padding: '7px 12px',
              fontSize: 12,
              borderRadius: 4,
              border: '1px solid var(--border)',
              backgroundColor: 'transparent',
              color: 'var(--text-primary)',
              cursor: loading || saving ? 'not-allowed' : 'pointer',
            }}
          >
            Preview in panel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={loading || saving}
            style={{
              padding: '7px 14px',
              fontSize: 12,
              borderRadius: 4,
              border: 'none',
              backgroundColor: 'var(--accent-blue)',
              color: '#fff',
              cursor: loading || saving ? 'not-allowed' : 'pointer',
              opacity: loading || saving ? 0.7 : 1,
            }}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
