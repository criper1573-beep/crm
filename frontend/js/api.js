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
