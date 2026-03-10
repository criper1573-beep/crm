// API calls

const BASE = typeof CONFIG !== 'undefined' ? CONFIG.api.base : '';

async function apiGetLeads() {
  try {
    const res = await fetch(`${BASE}/leads`);
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiGetLeads:', e);
    return null;
  }
}

async function apiGetLead(id) {
  try {
    const res = await fetch(`${BASE}/leads/${id}`);
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiGetLead:', e);
    return null;
  }
}

async function apiCreateLead(data) {
  try {
    const res = await fetch(`${BASE}/leads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiCreateLead:', e);
    return null;
  }
}

async function apiUpdateLead(id, data) {
  try {
    const res = await fetch(`${BASE}/leads/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiUpdateLead:', e);
    return null;
  }
}

async function apiDeleteLead(id) {
  try {
    const res = await fetch(`${BASE}/leads/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiDeleteLead:', e);
    return null;
  }
}

async function apiGetNotes(leadId) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/notes`);
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiGetNotes:', e);
    return null;
  }
}

async function apiCreateNote(leadId, text) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiCreateNote:', e);
    return null;
  }
}

async function apiDeleteNote(noteId) {
  try {
    const res = await fetch(`${BASE}/notes/${noteId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiDeleteNote:', e);
    return null;
  }
}

async function apiGetMessages(leadId) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/messages`);
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiGetMessages:', e);
    return null;
  }
}

async function apiCreateMessage(leadId, data) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiCreateMessage:', e);
    return null;
  }
}

async function apiCreateMessagesBulk(leadId, messages) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/messages/bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(messages),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiCreateMessagesBulk:', e);
    return null;
  }
}

async function apiDeleteMessage(id) {
  try {
    const res = await fetch(`${BASE}/messages/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiDeleteMessage:', e);
    return null;
  }
}

async function apiUpdateMessageDirection(id, direction) {
  try {
    const res = await fetch(`${BASE}/messages/${id}/direction`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ direction }),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiUpdateMessageDirection:', e);
    return null;
  }
}

async function apiSummarizeLead(leadId) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/summarize`, { method: 'POST' });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = body.detail;
      const msg = typeof detail === 'string' ? detail : Array.isArray(detail) && detail[0] ? (detail[0].msg || String(detail[0])) : (detail && detail.msg) || res.statusText;
      throw new Error(msg);
    }
    return { ...body, _status: res.status };
  } catch (e) {
    console.error('apiSummarizeLead:', e);
    throw e;
  }
}
if (typeof window !== 'undefined') window.apiSummarizeLead = apiSummarizeLead;

async function apiGenerateReply(leadId) {
  const base = (BASE || '').replace(/\/$/, '');
  const url = (base.endsWith('/api') ? base : base + '/api') + '/leads/' + leadId + '/generate-reply';
  const method = 'POST';
  // #region agent log
  fetch('http://127.0.0.1:7512/ingest/9610a248-e980-437d-9f27-76e38d464884',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'8d7168'},body:JSON.stringify({sessionId:'8d7168',location:'api.js:apiGenerateReply',message:'request',data:{url,method,leadId:leadId},hypothesisId:'H1 H2 H4 H5',timestamp:Date.now()})}).catch(()=>{});
  // #endregion
  const res = await fetch(url, { method });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = body.detail || res.statusText;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return body;
}
if (typeof window !== 'undefined') window.apiGenerateReply = apiGenerateReply;
