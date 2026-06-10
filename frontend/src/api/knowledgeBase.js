import axios from 'axios';

const API = '';

export async function fetchKnowledgeBasePages() {
  const r = await axios.get(`${API}/api/knowledge-base/pages`);
  return r.data?.pages || [];
}

export async function fetchKnowledgeBasePage(guideId) {
  const id = encodeURIComponent(String(guideId || '').trim());
  const r = await axios.get(`${API}/api/knowledge-base/${id}`);
  return r.data;
}

export async function saveKnowledgeBasePage(guideId, page) {
  const id = encodeURIComponent(String(guideId || '').trim());
  const r = await axios.put(`${API}/api/dev/knowledge-base/${id}`, page);
  return r.data;
}
