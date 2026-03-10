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

async function apiGetNotes(leadId, leadObjectId = null) {
  try {
    let url = `${BASE}/leads/${leadId}/notes`;
    if (leadObjectId != null) url += '?lead_object_id=' + encodeURIComponent(leadObjectId);
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiGetNotes:', e);
    return null;
  }
}

async function apiCreateNote(leadId, text, leadObjectId = null) {
  try {
    const body = { text };
    if (leadObjectId != null) body.lead_object_id = leadObjectId;
    const res = await fetch(`${BASE}/leads/${leadId}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiCreateNote:', e);
    return null;
  }
}

async function apiGetObjects(leadId) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/objects`);
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiGetObjects:', e);
    return null;
  }
}

async function apiCreateObject(leadId, data) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/objects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiCreateObject:', e);
    return null;
  }
}

async function apiUpdateObject(leadId, objectId, data) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/objects/${objectId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiUpdateObject:', e);
    return null;
  }
}

async function apiDeleteObject(leadId, objectId) {
  try {
    const res = await fetch(`${BASE}/leads/${leadId}/objects/${objectId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(res.statusText);
    return await res.json();
  } catch (e) {
    console.error('apiDeleteObject:', e);
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
  const url = (base ? base : '/api') + '/leads/' + leadId + '/generate-reply';
  const res = await fetch(url, { method: 'POST' });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = body.detail || res.statusText;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return body;
}
if (typeof window !== 'undefined') window.apiGenerateReply = apiGenerateReply;
