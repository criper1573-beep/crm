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
