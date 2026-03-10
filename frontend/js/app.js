// ─── DATA ─────────────────────────────────────────────────
const STATUS = {
  hot:    { label:'Горячий лид',   cls:'sbadge-hot',    side:'s-hot',    color:'var(--hot)',    fKey:'hot'    },
  client: { label:'Клиент',        cls:'sbadge-client', side:'s-client', color:'var(--client)', fKey:'client' },
  repeat: { label:'Повторно',      cls:'sbadge-repeat',  side:'s-repeat', color:'var(--repeat)', fKey:'repeat' },
  drain_g:{ label:'Слив горя',     cls:'sbadge-drain',   side:'s-drain',  color:'var(--muted)',  fKey:'drain'  },
  drain_m:{ label:'Слив MQL',      cls:'sbadge-drain',   side:'s-drain',  color:'var(--muted)',  fKey:'drain'  },
  drain_s:{ label:'Слив SQL',      cls:'sbadge-drain',   side:'s-drain',  color:'var(--muted)',  fKey:'drain'  },
  sql:    { label:'SQL',           cls:'sbadge-warn',    side:'s-repeat', color:'var(--warn)',   fKey:'repeat' },
};

const BUDGET = {
  lo:  { label:'< 30к',    cls:'btag-lo' },
  mid: { label:'30–100к',  cls:'btag-mid' },
  hi:  { label:'> 100к',   cls:'btag-hi' },
};

const funnelOrder = ['all', 'repeat', 'client', 'hot', 'sql', 'mql', 'lead', 'drain_hot', 'drain_sql', 'drain_mql'];

let leads = [];

function mapLeadFromApi(l) {
  return {
    ...l,
    link: l.avito_link ?? l.link ?? '',
    obj: l.object_type ?? l.obj ?? '',
    date: l.last_contact ?? l.date ?? '',
    calls: l.calls ?? [],
    msgs: l.msgs ?? [],
  };
}

async function reloadLeads() {
  const raw = await apiGetLeads();
  leads = (raw || []).map(mapLeadFromApi);
  updateStats();
  renderList();
}

function showSaveIndicator(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  let ind = container.querySelector('.save-indicator');
  if (!ind) {
    ind = document.createElement('span');
    ind.className = 'save-indicator';
    ind.textContent = '✓';
    container.appendChild(ind);
  }
  ind.classList.add('show');
  clearTimeout(ind._hideTimer);
  ind._hideTimer = setTimeout(() => { ind.classList.remove('show'); }, 1500);
}

function updateStatusInUI(leadId, newStatus) {
  const si = getStatusInfo(newStatus);
  const cfg = CONFIG.statuses && CONFIG.statuses[newStatus];
  const label = (cfg && cfg.label) || si.label;
  if (leadId === activeId) {
    const badge = document.querySelector('.detail-header .d-sub .sbadge');
    if (badge) {
      badge.textContent = label;
      badge.className = 'sbadge ' + (si.cls || '');
    }
    const btn = document.querySelector('.status-dropdown > button.dbtn');
    if (btn) btn.textContent = label + ' ▼';
  }
  const row = document.getElementById('lc-' + leadId);
  if (row) {
    const badge = row.querySelector('.sbadge');
    if (badge) {
      badge.textContent = label;
      badge.className = 'sbadge ' + (si.cls || '');
    }
    const classes = row.className.split(/\s+/).filter(c => c && !/^s-/.test(c));
    row.className = classes.concat(si.side || 's-drain').join(' ');
  }
  updateStats();
}

function getLeadPayloadForUpdate(l, overrides = {}) {
  return {
    name: l.name,
    phone: l.phone || '',
    extra_phones: l.extra_phones || '',
    avito_link: l.avito_link ?? l.link ?? '',
    max_link: l.max_link || '',
    tg_link: l.tg_link || '',
    address: l.address || '',
    object_type: l.object_type ?? l.obj ?? '',
    budget: l.budget,
    status: l.status,
    last_contact: l.last_contact ?? l.date ?? '',
    comment: l.comment || '',
    work_types: Array.isArray(l.work_types) ? l.work_types : (l.work_types ? JSON.parse(l.work_types || '[]') : []),
    description: l.description ?? '',
    deal_amount: l.deal_amount != null ? (typeof l.deal_amount === 'number' ? l.deal_amount : parseInt(l.deal_amount, 10) || null) : null,
    communication_done: !!l.communication_done,
    has_multiple_objects: !!l.has_multiple_objects,
    ...overrides,
  };
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function normalizeTgLink(s) {
  if (!s || !String(s).trim()) return '#';
  const t = String(s).trim();
  if (/^https?:\/\//i.test(t)) return t;
  const username = t.replace(/^@/, '').split(/[\s/]/)[0];
  return 'https://t.me/' + encodeURIComponent(username);
}

function startEditComment(id) {
  const l = leads.find(x => x.id === id);
  if (!l) return;
  const wrap = document.querySelector('.ai-comment-editable[data-lead-id="' + id + '"]');
  if (!wrap || wrap.querySelector('textarea')) return;
  const current = l.comment || '';
  wrap.innerHTML = '<textarea class="comment-edit-ta" rows="3"></textarea>';
  const ta = wrap.querySelector('textarea');
  ta.value = current;
  ta.focus();
  ta.addEventListener('blur', async function onBlur() {
    ta.removeEventListener('blur', onBlur);
    const newComment = ta.value.trim();
    const payload = getLeadPayloadForUpdate(l, { comment: newComment });
    const updated = await apiUpdateLead(id, payload);
    if (updated) l.comment = newComment;
    renderDetail();
  });
}

function toggleNewLeadForm() {
  const wrap = document.getElementById('newLeadFormWrap');
  if (wrap.style.display === 'none') {
    wrap.style.display = 'block';
    fillNewLeadFormSelects();
    document.getElementById('newLeadForm').reset();
  } else {
    wrap.style.display = 'none';
  }
}

function fillNewLeadFormSelects() {
  const objSelect = document.getElementById('newLeadObjectType');
  const budgetSelect = document.getElementById('newLeadBudget');
  const statusSelect = document.getElementById('newLeadStatus');
  if (!objSelect || !budgetSelect || !statusSelect) return;
  objSelect.innerHTML = CONFIG.objectTypes.map(t => `<option value="${t}">${t}</option>`).join('');
  budgetSelect.innerHTML = Object.entries(CONFIG.budgets).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('');
  statusSelect.innerHTML = Object.entries(CONFIG.statuses).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('');
}

async function submitNewLeadForm(e) {
  e.preventDefault();
  const form = e.target;
  const data = {
    name: form.name.value.trim(),
    phone: (form.phone.value || '').trim(),
    avito_link: (form.avito_link.value || '').trim(),
    address: (form.address.value || '').trim(),
    object_type: form.object_type.value,
    budget: form.budget.value,
    status: form.status.value,
    last_contact: '',
    comment: (form.comment.value || '').trim(),
  };
  if (!data.name) return false;
  const created = await apiCreateLead(data);
  if (!created) return false;
  await reloadLeads();
  document.getElementById('newLeadFormWrap').style.display = 'none';
  if (created.id) openLead(created.id);
  return false;
}

function cancelNewLeadForm() {
  document.getElementById('newLeadFormWrap').style.display = 'none';
}

// ─── CSV Import ───────────────────────────────────────────
let csvImportRows = [];

function toggleCsvImportModal() {
  const overlay = document.getElementById('csvImportOverlay');
  if (!overlay) return;
  if (overlay.style.display === 'none') {
    overlay.style.display = 'flex';
    csvImportRows = [];
    document.getElementById('csvImportPreview').style.display = 'none';
    document.getElementById('csvImportDrop').style.display = 'block';
    document.getElementById('csvImportDrop').onclick = () => document.getElementById('csvImportFileInput').click();
  } else {
    overlay.style.display = 'none';
    csvImportRows = [];
  }
}

function handleCsvDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add('dragover');
}

function handleCsvDragLeave(e) {
  e.currentTarget.classList.remove('dragover');
}

function handleCsvDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('dragover');
  const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (file && file.name.toLowerCase().endsWith('.csv')) processCsvFile(file);
}

function onCsvFileSelected(e) {
  const file = e.target && e.target.files[0];
  if (file) processCsvFile(file);
  e.target.value = '';
}

function parseCsvLine(line, sep) {
  const out = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') { inQuotes = !inQuotes; continue; }
    if (!inQuotes && c === sep) { out.push(cur.trim()); cur = ''; continue; }
    cur += c;
  }
  out.push(cur.trim());
  return out;
}

function mapBudget(val) {
  if (!val) return 'lo';
  const v = String(val).toLowerCase().replace(/\s/g, '');
  if (v === '<30к' || v === 'до30к') return 'lo';
  if (v === '30к-100к' || v === '30-100к') return 'mid';
  if (v === '>100к') return 'hi';
  return 'lo';
}

function mapStatus(val) {
  if (!val) return 'lead';
  const v = String(val).trim();
  const map = {
    'Горячий лид': 'hot', 'Клиент': 'client', 'Повторный клиент': 'repeat',
    'MQL': 'mql', 'SQL': 'sql', 'Лид': 'lead',
    'Слив MQL': 'drain_mql', 'Слив SQL': 'drain_sql', 'Слив горя': 'drain_hot', 'Слив горячий лид': 'drain_hot'
  };
  return map[v] || 'lead';
}

function isWorkTypeTrue(val) {
  return String(val === undefined ? '' : val).trim().toUpperCase() === 'TRUE';
}

async function processCsvFile(file) {
  const text = await file.text();
  const lines = text.split(/\r?\n/);
  if (lines.length < 4) { csvImportRows = []; showCsvPreview(); return; }
  const sep = (lines[0] || '').includes(';') ? ';' : ',';
  const headersRow0 = parseCsvLine(lines[0], sep).map(h => (h || '').replace(/^"|"$/g, '').trim());
  const row1Cells = parseCsvLine(lines[1], sep).map(c => (c || '').replace(/^"|"$/g, '').trim());
  const workTypeNames = row1Cells.slice(9, 16);
  const rows = [];
  for (let i = 3; i < lines.length; i++) {
    const line = (lines[i] || '').trim();
    if (!line) continue;
    const cells = parseCsvLine(lines[i], sep).map(c => (c !== undefined && c !== null ? c : '').toString().replace(/^"|"$/g, ''));
    const row = {};
    for (let j = 0; j < 9 && j < headersRow0.length; j++) {
      row[headersRow0[j] || 'col' + j] = cells[j] !== undefined ? cells[j] : '';
    }
    const name = (row['Имя'] || row['имя'] || '').trim();
    if (!name) continue;
    const workTypes = [];
    for (let k = 0; k < workTypeNames.length; k++) {
      if (workTypeNames[k] && isWorkTypeTrue(cells[9 + k])) workTypes.push(workTypeNames[k]);
    }
    rows.push({
      name,
      avito_link: (row['Ссылка'] || row['ссылка'] || '').trim(),
      phone: (row['Телефон'] || row['телефон'] || '').trim(),
      address: (row['Адрес'] || row['адрес'] || '').trim(),
      object_type: (row['Тип объекта'] || row['тип объекта'] || '').trim() || 'Квартира',
      budget: mapBudget(row['Бюджет'] || row['бюджет']),
      status: mapStatus(row['Статус'] || row['статус']),
      last_contact: (row['Последний контакт'] || row['последний контакт'] || '').trim(),
      comment: (row['Комментарий'] || row['комментарий'] || '').trim(),
      work_types: workTypes,
      description: '',
    });
  }
  const allLeads = await apiGetLeads();
  const mapped = (allLeads || []).map(mapLeadFromApi);
  for (const row of rows) {
    let existing = null;
    if (row.avito_link) existing = mapped.find(l => (l.avito_link || l.link || '').trim() === row.avito_link);
    if (!existing) existing = mapped.find(l => (l.name || '').trim() === row.name);
    if (existing) {
      row._action = 'update';
      row._existingId = existing.id;
      row._existingLead = existing;
    } else {
      row._action = 'new';
    }
  }
  csvImportRows = rows;
  showCsvPreview();
}

function showCsvPreview() {
  const preview = document.getElementById('csvImportPreview');
  const countEl = document.getElementById('csvImportPreviewCount');
  const drop = document.getElementById('csvImportDrop');
  if (!preview || !countEl) return;
  if (csvImportRows.length === 0) {
    preview.style.display = 'none';
    drop.style.display = 'block';
    return;
  }
  drop.style.display = 'none';
  preview.style.display = 'block';
  const newCount = csvImportRows.filter(r => r._action === 'new').length;
  const updateCount = csvImportRows.filter(r => r._action === 'update').length;
  countEl.innerHTML = `Новых лидов: <strong>${newCount}</strong><br>Будет обновлено: <strong>${updateCount}</strong>`;
}

async function doCsvImport() {
  for (const row of csvImportRows) {
    if (row._action === 'update') {
      const existing = row._existingLead;
      const payload = {
        name: existing.name,
        phone: row.phone,
        avito_link: existing.avito_link ?? existing.link ?? '',
        address: row.address,
        object_type: existing.object_type ?? existing.obj ?? '',
        budget: row.budget,
        status: row.status,
        last_contact: row.last_contact,
        comment: existing.comment ?? '',
        work_types: row.work_types,
        description: existing.description ?? '',
      };
      await apiUpdateLead(row._existingId, payload);
      if (row.comment) {
        const notes = await apiGetNotes(row._existingId);
        if (notes && notes.length === 0) await apiCreateNote(row._existingId, row.comment);
      }
    } else {
      const leadData = {
        name: row.name,
        avito_link: row.avito_link,
        phone: row.phone,
        address: row.address,
        object_type: row.object_type,
        budget: row.budget,
        status: row.status,
        last_contact: row.last_contact,
        comment: '',
        work_types: row.work_types,
        description: '',
      };
      const created = await apiCreateLead(leadData);
      if (created && created.id && row.comment) await apiCreateNote(created.id, row.comment);
    }
  }
  csvImportRows = [];
  toggleCsvImportModal();
  await reloadLeads();
}

function cancelCsvImport() {
  csvImportRows = [];
  toggleCsvImportModal();
}

function toggleStatusDropdown(e) {
  e.stopPropagation();
  const wrap = document.getElementById('statusDropdown');
  const menu = document.getElementById('statusDropdownMenu');
  const isOpen = menu && menu.style.display === 'block';
  document.querySelectorAll('.status-dropdown-menu').forEach(m => { m.style.display = 'none'; });
  if (!isOpen && menu && wrap) {
    const btn = wrap.querySelector('button');
    const rect = btn ? btn.getBoundingClientRect() : e.currentTarget.getBoundingClientRect();
    if (menu.parentNode !== document.body) document.body.appendChild(menu);
    menu.style.position = 'fixed';
    menu.style.left = rect.left + 'px';
    menu.style.top = (rect.bottom + 4) + 'px';
    menu.style.display = 'block';
    setTimeout(() => {
      const close = () => {
        if (wrap && menu.parentNode === document.body) wrap.appendChild(menu);
        menu.style.display = 'none';
        document.removeEventListener('click', close);
      };
      document.addEventListener('click', close);
    }, 0);
  }
}

async function selectStatus(id, newStatus, e) {
  e.stopPropagation();
  const menu = document.getElementById('statusDropdownMenu');
  if (menu) menu.style.display = 'none';
  const l = leads.find(x => x.id === id);
  if (!l) return;
  const payload = getLeadPayloadForUpdate(l, { status: newStatus });
  const updated = await apiUpdateLead(id, payload);
  if (!updated) return;
  l.status = newStatus;
  updateStatusInUI(id, newStatus);
}

async function deleteLead(id) {
  if (!confirm('Удалить лид? Это действие нельзя отменить')) return;
  const ok = await apiDeleteLead(id);
  if (!ok) return;
  await reloadLeads();
  if (activeId === id) {
    activeId = null;
    document.getElementById('detail').innerHTML = `
      <div class="empty"><div class="empty-ico">🏗️</div><div>Выберите лида</div></div>
    `;
  }
}

// ─── STATE ─────────────────────────────────────────────────
const CRM_STORAGE_KEY = 'crm_state';
let activeId = null;
let activeTab = 'overview';
let currentFilter = 'all';
let currentPeriod = 'month';
let activeObjectId = null;
let headerEditMode = false;

function saveState() {
  try {
    sessionStorage.setItem(CRM_STORAGE_KEY, JSON.stringify({
      activeId,
      activeTab,
      currentFilter,
      currentPeriod,
      activeObjectId,
    }));
  } catch (e) {}
}

function loadState() {
  try {
    const raw = sessionStorage.getItem(CRM_STORAGE_KEY);
    if (!raw) return;
    const s = JSON.parse(raw);
    if (s.currentPeriod) currentPeriod = s.currentPeriod;
    if (s.currentFilter) currentFilter = s.currentFilter;
    if (s.activeId != null) activeId = s.activeId;
    if (s.activeTab) activeTab = s.activeTab;
    if (s.activeObjectId != null) activeObjectId = s.activeObjectId;
  } catch (e) {}
}

function getPeriodRange(periodKey) {
  const today = new Date();
  const y = today.getFullYear();
  const m = today.getMonth();
  const d = today.getDate();
  const toStr = (date) => date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
  let startDate;
  let endDate = toStr(today);
  if (periodKey === 'month') {
    startDate = y + '-' + String(m + 1).padStart(2, '0') + '-01';
  } else {
    const daysBack = periodKey === 'week' ? 7 : periodKey === 'prev_month' ? 30 : periodKey === 'quarter' ? 90 : periodKey === 'year' ? 365 : 30;
    const start = new Date(today);
    start.setDate(start.getDate() - daysBack);
    startDate = toStr(start);
  }
  return { startDate, endDate };
}

function lastContactToYmd(str) {
  if (!str || typeof str !== 'string') return '';
  const s = str.trim();
  const iso = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (iso) return iso[1] + '-' + iso[2].padStart(2, '0') + '-' + iso[3].padStart(2, '0');
  const dmy = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})/);
  if (dmy) return dmy[3] + '-' + dmy[2].padStart(2, '0') + '-' + dmy[1].padStart(2, '0');
  return '';
}

function getLeadsForPeriod() {
  const { startDate, endDate } = getPeriodRange(currentPeriod);
  return leads.filter(l => {
    const dateYmd = lastContactToYmd(l.last_contact || l.date || '') || (l.created_at || '').slice(0, 10);
    if (!dateYmd) return false;
    return dateYmd >= startDate && dateYmd <= endDate;
  });
}

function setPeriod(periodKey) {
  currentPeriod = periodKey;
  document.querySelectorAll('.period-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-period') === periodKey);
  });
  saveState();
  updateStats();
}

// ─── STATUS CONFIG ──────────────────────────────────────────
const funnelConfig = [
  { key:'hot',    label:'🔥 Горячий лид',  color:'var(--hot)' },
  { key:'client', label:'✅ Клиент',        color:'var(--client)' },
  { key:'repeat', label:'🔄 Повторно',      color:'var(--repeat)' },
  { key:'sql',    label:'📋 SQL',           color:'var(--warn)' },
  { key:'drain',  label:'📉 Слив',          color:'var(--muted)' },
];

function getStatusGroup(s) {
  if (!s) return s;
  if (['drain_g', 'drain_m', 'drain_s', 'drain_mql', 'drain_sql', 'drain_hot'].includes(s) || String(s).startsWith('drain')) return 'drain';
  return s;
}

function getStatusInfo(s) {
  return STATUS[s] || STATUS['drain_g'];
}

// ─── STATS ─────────────────────────────────────────────────
function updateStats() {
  const leadsForPeriod = getLeadsForPeriod();
  const groups = {hot:0,client:0,repeat:0,drain:0,sql:0};
  leads.forEach(l => { const g = getStatusGroup(l.status); if(groups[g]!==undefined) groups[g]++; });
  document.getElementById('cntHot').textContent = groups.hot;
  document.getElementById('cntClient').textContent = groups.client;
  document.getElementById('cntAll').textContent = leads.length;
  const periodGroups = {hot:0,client:0,repeat:0,drain:0,sql:0};
  leadsForPeriod.forEach(l => { const g = getStatusGroup(l.status); if(periodGroups[g]!==undefined) periodGroups[g]++; });
  document.getElementById('s1').textContent = periodGroups.hot;
  document.getElementById('s2').textContent = periodGroups.client;
  document.getElementById('s3').textContent = periodGroups.repeat + periodGroups.sql;
  document.getElementById('s4').textContent = periodGroups.drain;

  const revenueLeads = leadsForPeriod.filter(l => l.status === 'client' || l.status === 'repeat');
  const revenue = revenueLeads.reduce((sum, l) => {
    const v = (l.has_multiple_objects && l.objects && l.objects.length)
      ? (l.objects || []).reduce((s, o) => s + (Number(o.deal_amount) || 0), 0)
      : (Number(l.deal_amount) || 0);
    return sum + v;
  }, 0);
  const revenueEl = document.getElementById('revenueTotal');
  if (revenueEl) revenueEl.textContent = formatDealAmount(revenue) || '0 ₽';

  // funnel in sidebar: counts by selected period (same as analytics)
  const sfl = document.getElementById('sidebarFunnelList');
  if (sfl) {
    const total = leadsForPeriod.length;
    const pctAll = total ? 100 : 0;
    const activeAll = currentFilter === 'all';
    let html = `<div class="funnel-item ${activeAll ? 'active' : ''}" onclick="setFilter('all')">
      <div class="fi-dot" style="background:var(--accent)"></div>
      <div class="fi-label">Все</div>
      <div class="fi-count">${total}</div>
      <div class="fi-pct" style="color:var(--accent)">${pctAll}%</div>
    </div>`;
    if (CONFIG.statuses) {
      funnelOrder.filter(k => k !== 'all').forEach(key => {
        const cfg = CONFIG.statuses[key];
        if (!cfg) return;
        const cnt = leadsForPeriod.filter(l => l.status === key).length;
        const pct = total ? Math.round(cnt / total * 100) : 0;
        const color = (cfg && cfg.color) || 'var(--text2)';
        const isActive = currentFilter === key;
        html += `<div class="funnel-item ${isActive ? 'active' : ''}" onclick="setFilter('${escapeHtml(key)}')">
          <div class="fi-dot" style="background:${color}"></div>
          <div class="fi-label">${escapeHtml(cfg.label)}</div>
          <div class="fi-count">${cnt}</div>
          <div class="fi-pct" style="color:${color}">${pct}%</div>
        </div>`;
      });
    }
    sfl.innerHTML = html;
  }
  // work types stats in right panel (by period)
  const wtEl = document.getElementById('workTypesStats');
  if (wtEl && CONFIG.workTypes) {
    const total = leadsForPeriod.length;
    wtEl.innerHTML = CONFIG.workTypes.map(wt => {
      const cnt = leadsForPeriod.filter(l => Array.isArray(l.work_types) && l.work_types.includes(wt)).length;
      const pct = total ? Math.round(cnt / total * 100) : 0;
      return `<div class="work-type-stat-row">
        <div style="display:flex;justify-content:space-between;font-size:9px;margin-bottom:3px">
          <span style="color:var(--text2)">${escapeHtml(wt)}</span>
          <span style="color:var(--accent)">${cnt} · ${pct}%</span>
        </div>
        <div class="work-type-stat-bar"><div class="work-type-stat-fill" style="width:${pct}%"></div></div>
      </div>`;
    }).join('');
  }

  // budget bars (by period)
  const budgets = {lo:0,mid:0,hi:0};
  leadsForPeriod.forEach(l => { if(budgets[l.budget]!==undefined) budgets[l.budget]++; });
  document.getElementById('budgetBars').innerHTML = [
    {k:'hi',label:'> 100к',color:'var(--accent2)'},
    {k:'mid',label:'30–100к',color:'var(--accent)'},
    {k:'lo',label:'< 30к',color:'var(--muted)'},
  ].map(b => {
    const pct = leadsForPeriod.length ? Math.round(budgets[b.k]/leadsForPeriod.length*100) : 0;
    return `<div style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;font-size:9px;margin-bottom:3px">
        <span style="color:var(--text2)">${b.label}</span>
        <span style="color:${b.color}">${budgets[b.k]} лидов</span>
      </div>
      <div style="height:4px;background:var(--border);border-radius:2px;overflow:hidden">
        <div style="height:100%;width:${pct}%;background:${b.color};border-radius:2px;transition:width 1s ease"></div>
      </div>
    </div>`;
  }).join('');

  // Требуют внимания: условие 1 — последнее сообщение direction=in; условие 2 — не слив и (последнее исх. >24ч назад или нет сообщений и лид создан >24ч назад)
  function isDrain(s) { return getStatusGroup(s) === 'drain'; }
  function daysAgo(dateStr) {
    if (!dateStr) return null;
    const d = new Date(dateStr.replace(' ', 'T'));
    if (isNaN(d.getTime())) return null;
    return Math.floor((Date.now() - d.getTime()) / (24 * 60 * 60 * 1000));
  }
  const alertLeads = leads.filter(l => {
    if (l.communication_done) return false;
    const lastDir = (l.last_message_direction || '').toLowerCase();
    const lastDate = l.last_message_date || '';
    const hasMessages = !!lastDir;
    const cond1 = lastDir === 'in';
    const notDrain = !isDrain(l.status);
    const lastOutMoreThan24h = lastDir === 'out' && daysAgo(lastDate) !== null && daysAgo(lastDate) >= 1;
    const noMessagesLeadOld = !hasMessages && daysAgo(l.created_at) !== null && daysAgo(l.created_at) >= 1;
    const cond2 = notDrain && (lastOutMoreThan24h || noMessagesLeadOld);
    return cond1 || cond2;
  }).map(l => {
    const lastDir = (l.last_message_direction || '').toLowerCase();
    const reason = lastDir === 'in' ? 'Клиент написал — нет ответа' : (() => {
      const refDate = lastDir === 'out' ? l.last_message_date : (l.created_at || '');
      const days = daysAgo(refDate);
      return days !== null ? 'Нет активности ' + days + ' дн.' : 'Нет активности';
    })();
    return { ...l, _reason: reason };
  });
  const alertsEl = document.getElementById('alertsList');
  if (alertsEl) {
    alertsEl.innerHTML = alertLeads.length ? alertLeads.map(l => {
      const cfg = CONFIG.statuses && CONFIG.statuses[l.status];
      const color = (cfg && cfg.color) || 'var(--text2)';
      return `<div class="alert-item" onclick="openLead(${l.id})">
        <div class="ai-top"><span>${escapeHtml(l.name)}</span><span style="font-size:9px;font-weight:500;color:${color}">${escapeHtml((cfg && cfg.label) || l.status)}</span></div>
        <div class="ai-sub">${escapeHtml(l._reason)}</div>
      </div>`;
    }).join('') : '<div style="font-size:10px;color:var(--muted);text-align:center;padding:10px">Всё обработано 👍</div>';
  }
}

// ─── RENDER LIST ───────────────────────────────────────────
function renderList() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const leadsInPeriod = getLeadsForPeriod();
  const filtered = leadsInPeriod.filter(l => {
    const matchFilter = currentFilter === 'all' ||
      (CONFIG.statuses && currentFilter in CONFIG.statuses ? l.status === currentFilter : getStatusGroup(l.status) === currentFilter);
    const matchSearch = !q || (l.name || '').toLowerCase().includes(q) || (l.address || '').toLowerCase().includes(q) || (l.comment || '').toLowerCase().includes(q);
    return matchFilter && matchSearch;
  });

  const el = document.getElementById('leadsList');
  el.innerHTML = filtered.map(l => {
    const si = getStatusInfo(l.status);
    const bi = BUDGET[l.budget];
    const hasNewMsg = (l.msgs && l.msgs.length > 0 && !l.msgs[l.msgs.length-1].out);
    return `<div class="lead-card ${si.side} ${activeId===l.id?'active':''}" id="lc-${l.id}" onclick="openLead(${l.id})">
      ${hasNewMsg ? '<div style="position:absolute;top:12px;right:12px;width:7px;height:7px;border-radius:50%;background:var(--hot);animation:pulse 1.5s infinite"></div>' : ''}
      <div class="lc-row">
        <div class="lc-name">${l.name}</div>
        <div class="lc-date">${l.date}</div>
      </div>
      <div class="lc-meta">
        <span class="sbadge ${si.cls}">${si.label}</span>
        ${bi ? `<span class="btag ${bi.cls}">${bi.label}</span>` : ''}
        ${l.obj ? `<span class="otag">${l.obj}</span>` : ''}
      </div>
    </div>`;
  }).join('');
}

function setFilter(f) {
  currentFilter = f;
  saveState();
  renderList();
  updateStats();
}

function filterLeads() { renderList(); }

// ─── MOBILE PANELS ──────────────────────────────────────────
function toggleMobilePanel(which) {
  const body = document.body;
  if (which === 'sidebar') {
    body.classList.toggle('mobile-sidebar-open');
    body.classList.remove('mobile-rpanel-open');
  } else if (which === 'rpanel') {
    body.classList.toggle('mobile-rpanel-open');
    body.classList.remove('mobile-sidebar-open');
  }
}
function closeMobilePanels() {
  document.body.classList.remove('mobile-sidebar-open', 'mobile-rpanel-open');
}

// ─── OPEN LEAD ─────────────────────────────────────────────
function openLead(id) {
  activeId = id;
  activeTab = 'overview';
  headerEditMode = false;
  const l = leads.find(x => x.id === id);
  if (l && l.has_multiple_objects && l.objects && l.objects.length) {
    activeObjectId = l.objects[0].id;
  } else {
    activeObjectId = null;
  }
  saveState();
  closeMobilePanels();
  renderList();
  renderDetail();
}

function renderHeaderView(l) {
  const si = getStatusInfo(l.status);
  return `
    <div class="d-avatar">${(l.name || ' ')[0]}</div>
    <div class="d-header-center">
      <div class="d-name-wrap" id="dNameWrap-${l.id}"><span class="d-name d-name-editable" data-lead-id="${l.id}" onclick="startEditLeadName(${l.id})" title="Нажмите для редактирования">${escapeHtml(l.name || '')}</span></div>
      <div class="d-sub d-sub-header">
        ${l.phone ? `<a href="tel:${(l.phone).replace(/[^\d+]/g, '')}" class="d-sub-phone" title="Позвонить">📞 ${escapeHtml(l.phone)}</a>` : ''}
        <span class="sbadge ${si.cls}">${si.label}</span>
      </div>
    </div>
    <div class="d-actions">
      ${l.phone ? `<a href="tel:${(l.phone).replace(/[^\d+]/g, '')}" class="dbtn dbtn-tel" title="Позвонить">📞</a>` : ''}
      ${(l.avito_link || l.link) ? `<a href="${escapeHtml((l.avito_link || l.link).trim())}" target="_blank" rel="noopener" class="dbtn">🔗 Авито</a>` : ''}
      ${(() => { const u = (l.max_link || '').trim(); return u && (u.startsWith('http://') || u.startsWith('https://')) ? `<a href="${escapeHtml(u)}" target="_blank" rel="noopener" class="dbtn">МАХ</a>` : ''; })()}
      ${(l.tg_link || '').trim() ? `<a href="${normalizeTgLink(l.tg_link)}" target="_blank" rel="noopener" class="dbtn dbtn-tel">TG</a>` : ''}
      <div class="status-dropdown" id="statusDropdown">
        <button type="button" class="dbtn" onclick="toggleStatusDropdown(event)">${si.label} ▼</button>
        <div class="status-dropdown-menu" id="statusDropdownMenu">
          ${Object.entries(CONFIG.statuses).map(([k, v]) => `<button type="button" class="status-dropdown-item" data-status="${k}" style="color:${v.color};--status-bg:${v.bg}" onclick="selectStatus(${l.id}, '${k}', event)"><span class="status-dropdown-dot" style="background:${v.color}"></span>${v.label}</button>`).join('')}
        </div>
      </div>
      <button type="button" class="dbtn" onclick="toggleHeaderEdit()">Редактировать</button>
      <label class="toggle-wrap d-header-toggle" title="У клиента несколько объектов"><input type="checkbox" ${l.has_multiple_objects ? 'checked' : ''} onchange="toggleHasMultipleObjects(${l.id}, this.checked)"><span class="toggle-slider"></span><span class="toggle-label">Несколько объектов</span></label>
      <button type="button" class="dbtn" onclick="deleteLead(${l.id})" style="color:var(--hot);border-color:rgba(255,77,109,0.5)">Удалить лид</button>
    </div>`;
}

function renderHeaderEdit(l) {
  const statusOpts = CONFIG.statuses ? Object.entries(CONFIG.statuses).map(([k, v]) => `<option value="${escapeHtml(k)}" ${l.status === k ? 'selected' : ''}>${escapeHtml(v.label)}</option>`).join('') : '';
  return `
    <div class="d-avatar">${(l.name || ' ')[0]}</div>
    <div class="d-header-edit-fields">
      <input type="text" id="headerEditName" class="d-header-edit-input" value="${escapeHtml(l.name || '')}" placeholder="Имя">
      <input type="text" id="headerEditPhone" class="d-header-edit-input" value="${escapeHtml(l.phone || '')}" placeholder="Телефон">
      <input type="text" id="headerEditAvito" class="d-header-edit-input" value="${escapeHtml((l.avito_link || l.link || '').trim())}" placeholder="Ссылка Авито">
      <input type="text" id="headerEditMax" class="d-header-edit-input" value="${escapeHtml((l.max_link || '').trim())}" placeholder="Ссылка МАХ">
      <input type="text" id="headerEditTg" class="d-header-edit-input" value="${escapeHtml((l.tg_link || '').trim())}" placeholder="Ссылка TG">
      <select id="headerEditStatus" class="d-header-edit-select">${statusOpts}</select>
    </div>
    <div class="d-actions">
      <button type="button" class="dbtn primary" onclick="saveHeaderEdit(${l.id})">Сохранить</button>
      <button type="button" class="dbtn" onclick="cancelHeaderEdit()">Отмена</button>
    </div>`;
}

function toggleHeaderEdit() {
  headerEditMode = true;
  renderDetail();
}

function cancelHeaderEdit() {
  headerEditMode = false;
  renderDetail();
}

async function saveHeaderEdit(leadId) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const name = (document.getElementById('headerEditName') && document.getElementById('headerEditName').value || '').trim();
  const phone = (document.getElementById('headerEditPhone') && document.getElementById('headerEditPhone').value || '').trim();
  const avito_link = (document.getElementById('headerEditAvito') && document.getElementById('headerEditAvito').value || '').trim();
  const max_link = (document.getElementById('headerEditMax') && document.getElementById('headerEditMax').value || '').trim();
  const tg_link = (document.getElementById('headerEditTg') && document.getElementById('headerEditTg').value || '').trim();
  const statusEl = document.getElementById('headerEditStatus');
  const status = statusEl ? statusEl.value : l.status;
  const payload = getLeadPayloadForUpdate(l, { name: name || l.name, phone, avito_link, max_link, tg_link, status });
  const updated = await apiUpdateLead(leadId, payload);
  if (updated) {
    l.name = payload.name;
    l.phone = payload.phone;
    l.avito_link = payload.avito_link;
    l.max_link = payload.max_link;
    l.tg_link = payload.tg_link;
    l.status = payload.status;
    l.link = payload.avito_link;
    headerEditMode = false;
    renderDetail();
    renderList();
    updateStats();
  }
}

async function toggleHasMultipleObjects(leadId, checked) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const payload = getLeadPayloadForUpdate(l, { has_multiple_objects: checked });
  const updated = await apiUpdateLead(leadId, payload);
  if (updated) {
    l.has_multiple_objects = !!checked;
    if (updated.objects) l.objects = updated.objects;
    if (checked && (!l.objects || l.objects.length === 0) && updated.objects && updated.objects.length > 0) {
      activeObjectId = updated.objects[0].id;
    } else if (!checked) {
      activeObjectId = null;
    }
    saveState();
    renderDetail();
  }
}

function renderDetail() {
  const l = leads.find(x => x.id === activeId);
  if(!l) return;
  const si = getStatusInfo(l.status);
  const bi = BUDGET[l.budget];
  const detail = document.getElementById('detail');

  const headerHtml = headerEditMode ? renderHeaderEdit(l) : renderHeaderView(l);
  detail.innerHTML = `
    <div class="detail-header fade-in" id="detailHeader">
      ${headerHtml}
    </div>
    <div class="dtabs">
      <div class="dtab ${activeTab==='overview'?'active':''}" onclick="switchTab('overview')">🗂 Обзор</div>
      <div class="dtab ${activeTab==='msgs'?'active':''}" onclick="switchTab('msgs')">💬 Переписка</div>
      <div class="dtab ${activeTab==='calls'?'active':''}" onclick="switchTab('calls')">📞 Звонки (${l.calls.length})</div>
    </div>
    <div class="tab-body fade-in" id="tabBody">${renderTab(l)}</div>
  `;
  if (activeTab === 'overview') setTimeout(() => loadNotesIntoFeed(activeId, activeObjectId), 0);
  if (activeTab === 'msgs') setTimeout(() => loadMessagesIntoFeed(activeId), 0);
}

function switchTab(tab) {
  activeTab = tab;
  saveState();
  const l = leads.find(x => x.id === activeId);
  document.querySelectorAll('.dtab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.dtab').forEach(t => {
    if((tab==='overview'&&t.textContent.includes('Обзор'))||
       (tab==='msgs'&&t.textContent.includes('Переписка'))||
       (tab==='calls'&&t.textContent.includes('Звонки'))) t.classList.add('active');
  });
  const tb = document.getElementById('tabBody');
  tb.innerHTML = renderTab(l);
  tb.classList.remove('fade-in'); void tb.offsetWidth; tb.classList.add('fade-in');
  if (tab === 'overview') loadNotesIntoFeed(activeId, activeObjectId);
  if (tab === 'msgs') setTimeout(() => loadMessagesIntoFeed(activeId), 0);
}

async function loadLastContactFromMessages(leadId) {
  const wrap = document.getElementById('cardField-' + leadId + '-last_contact');
  const input = wrap && wrap.querySelector('input.aif-edit-input');
  if (!input) return;
  const messages = await apiGetMessages(leadId);
  if (messages && messages.length > 0) {
    const maxDate = messages.reduce((max, m) => {
      const d = m.created_at || '';
      return d > max ? d : max;
    }, '');
    if (maxDate && !input.value.trim()) input.value = formatNoteDate(maxDate);
  }
}

async function saveLastContactOnBlur(inputEl, leadId) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const value = (inputEl && inputEl.value || '').trim();
  await updateOverviewField(leadId, null, 'last_contact', value);
  showSaveIndicator('cardField-' + leadId + '-last_contact');
  const row = document.getElementById('lc-' + leadId);
  if (row) { const dateEl = row.querySelector('.lc-date'); if (dateEl) dateEl.textContent = value || '—'; }
  updateStats();
}

function initDescriptionBlur(leadId, objectId = null) {
  const suffix = objectId != null ? objectId : 'l';
  const ta = document.getElementById('descriptionTa-' + leadId + '-' + suffix);
  if (!ta || ta.dataset.blurInited) return;
  ta.dataset.blurInited = '1';
  ta.addEventListener('blur', async function onBlur() {
    const l = leads.find(x => x.id === leadId);
    if (!l) return;
    const value = ta.value.trim();
    const cur = objectId != null ? (l.objects || []).find(o => o.id === objectId) : l;
    if (!cur || String(cur.description || '') === value) return;
    await updateOverviewField(leadId, objectId, 'description', value);
  });
}

async function requestLeadSummary(leadId) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const fn = window.apiSummarizeLead;
  if (typeof fn !== 'function') {
    alert('Модуль API не загружен. Обновите страницу (F5).');
    return;
  }
  const btn = document.getElementById('btnSummarize-' + leadId);
  const origText = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Запуск…'; }
  try {
    const res = await fn(leadId);
    const isStarted = res && (res._status === 202 || res.status === 'started');
    if (isStarted) {
      if (btn) btn.textContent = 'В фоне…';
      alert('Резюме генерируется в фоне (до 3 мин). Результат сохранится в описание лида. Можно закрыть вкладку — при следующем открытии карточки описание обновится.');
      startSummaryPolling(leadId);
    } else if (res && res.description != null) {
      l.description = res.description;
      const suffix = activeObjectId != null ? activeObjectId : 'l';
      if (l.has_multiple_objects && activeObjectId) {
        const obj = (l.objects || []).find(o => o.id === activeObjectId);
        if (obj) { obj.description = res.description; apiUpdateObject(leadId, activeObjectId, { ...obj, description: res.description }); }
      }
      const ta = document.getElementById('descriptionTa-' + leadId + '-' + suffix);
      if (ta) ta.value = res.description;
      showSaveIndicator('cardField-' + leadId + '-' + suffix + '-description');
    }
  } catch (e) {
    alert(e.message || 'Ошибка при запуске генерации резюме');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = origText; }
  }
}

function startSummaryPolling(leadId) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const maxAttempts = 24;
  const intervalMs = 15000;
  let attempts = 0;
  const timer = setInterval(async () => {
    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(timer);
      return;
    }
    const updated = await apiGetLead(leadId);
    if (updated && updated.description && String(updated.description).trim() !== String(l.description || '').trim()) {
      l.description = updated.description;
      if (l.has_multiple_objects && activeObjectId) {
        const obj = (l.objects || []).find(o => o.id === activeObjectId);
        if (obj) { obj.description = updated.description; apiUpdateObject(leadId, activeObjectId, { ...obj, description: updated.description }); }
      }
      const suffix = activeObjectId != null ? activeObjectId : 'l';
      const ta = document.getElementById('descriptionTa-' + leadId + '-' + suffix);
      if (ta) ta.value = updated.description;
      showSaveIndicator('cardField-' + leadId + '-' + suffix + '-description');
      clearInterval(timer);
    }
  }, intervalMs);
}

async function toggleWorkType(leadId, workTypeName, checked) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  let arr = Array.isArray(l.work_types) ? [...l.work_types] : [];
  if (checked) { if (!arr.includes(workTypeName)) arr.push(workTypeName); }
  else arr = arr.filter(x => x !== workTypeName);
  const payload = getLeadPayloadForUpdate(l, { work_types: arr });
  const updated = await apiUpdateLead(leadId, payload);
  if (updated) {
    l.work_types = arr;
    showSaveIndicator('cardField-' + leadId + '-work_types');
  }
}

function formatDealAmount(n) {
  if (n == null || n === '' || isNaN(Number(n))) return '';
  const num = parseInt(String(n).replace(/\D/g, ''), 10);
  if (isNaN(num)) return '';
  return String(num).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' ₽';
}

function filterDealAmountInput(inputEl) {
  inputEl.value = (inputEl.value || '').replace(/\D/g, '');
}

async function saveDealAmountOnBlur(inputEl) {
  const leadId = parseInt(inputEl.getAttribute('data-lead-id'), 10);
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const digits = (inputEl.value || '').replace(/\D/g, '');
  const value = digits ? parseInt(digits, 10) : null;
  const payload = getLeadPayloadForUpdate(l, { deal_amount: value });
  const updated = await apiUpdateLead(leadId, payload);
  if (updated) {
    l.deal_amount = value;
    showSaveIndicator('cardField-' + leadId + '-deal_amount');
    updateStats();
  }
}

function startEditLeadName(leadId) {
  const wrap = document.getElementById('dNameWrap-' + leadId);
  const l = leads.find(x => x.id === leadId);
  if (!wrap || !l) return;
  const oldName = l.name || '';
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'd-name-input';
  input.value = oldName;
  input.dataset.leadId = String(leadId);
  wrap.innerHTML = '';
  wrap.appendChild(input);
  input.focus();
  input.select();
  function commit() {
    const newName = (input.value || '').trim();
    if (!newName) {
      wrap.innerHTML = `<span class="d-name d-name-editable" data-lead-id="${leadId}" onclick="startEditLeadName(${leadId})" title="Нажмите для редактирования">${escapeHtml(oldName)}</span>`;
      return;
    }
    input.removeEventListener('blur', onBlur);
    input.removeEventListener('keydown', onKeyDown);
    (async () => {
      const payload = getLeadPayloadForUpdate(l, { name: newName });
      const updated = await apiUpdateLead(leadId, payload);
      if (updated) {
        l.name = newName;
        wrap.innerHTML = `<span class="d-name d-name-editable" data-lead-id="${leadId}" onclick="startEditLeadName(${leadId})" title="Нажмите для редактирования">${escapeHtml(newName)}</span>`;
        const listRow = document.querySelector('#lc-' + leadId + ' .lc-name');
        if (listRow) listRow.textContent = newName;
        const avatar = document.querySelector('.detail-header .d-avatar');
        if (avatar) avatar.textContent = (newName[0] || '').toUpperCase();
        showSaveIndicator('dNameWrap-' + leadId);
      } else {
        wrap.innerHTML = `<span class="d-name d-name-editable" data-lead-id="${leadId}" onclick="startEditLeadName(${leadId})" title="Нажмите для редактирования">${escapeHtml(oldName)}</span>`;
      }
    })();
  }
  function onBlur() { commit(); }
  function onKeyDown(e) { if (e.key === 'Enter') { e.preventDefault(); input.blur(); } }
  input.addEventListener('blur', onBlur);
  input.addEventListener('keydown', onKeyDown);
}

async function updateLeadField(leadId, field, value) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const payload = getLeadPayloadForUpdate(l, { [field]: value });
  const updated = await apiUpdateLead(leadId, payload);
  if (updated) {
    l[field] = value;
    if (field === 'object_type') l.obj = value;
    if (field === 'status') updateStatusInUI(leadId, value);
    if (field === 'communication_done') { updateStats(); showSaveIndicator('cardField-' + leadId + '-communication_done'); }
    else showSaveIndicator('cardField-' + leadId + '-' + field);
  }
}

async function loadNotesIntoFeed(leadId, objectId = null) {
  loadLastContactFromMessages(leadId);
  const suffix = objectId != null ? objectId : 'l';
  initDescriptionBlur(leadId, objectId);
  const el = document.getElementById('notesList-' + leadId + '-' + suffix);
  if (!el) return;
  const notes = await apiGetNotes(leadId, objectId);
  if (notes === null) { el.textContent = 'Ошибка загрузки'; return; }
  if (!notes.length) { el.innerHTML = '<div class="notes-empty">Нет заметок</div>'; return; }
  const objParam = objectId != null ? objectId : 'null';
  el.innerHTML = notes.map(n => {
    const dt = formatNoteDate(n.created_at);
    return `<div class="note-item" data-note-id="${n.id}">
      <span class="note-date">${escapeHtml(dt)}</span>
      <span class="note-text">${escapeHtml(n.text)}</span>
      <button type="button" class="note-delete" onclick="deleteNote(${n.id}, ${leadId}, ${objParam})" title="Удалить">×</button>
    </div>`;
  }).join('');
}

function formatNoteDate(createdAt) {
  if (!createdAt) return '—';
  const s = String(createdAt);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}`;
  return s;
}

function formatCreatedDate(createdAt) {
  if (!createdAt) return '—';
  const s = String(createdAt).trim();
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  const d = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})/);
  if (d) return `${d[1].padStart(2,'0')}.${d[2].padStart(2,'0')}.${d[3]}`;
  const d2 = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2})/);
  if (d2) return `${d2[1].padStart(2,'0')}.${d2[2].padStart(2,'0')}.20${d2[3]}`;
  return s.slice(0, 10) || '—';
}

async function addNote(leadId, text, objectId = null) {
  const created = await apiCreateNote(leadId, text, objectId);
  if (!created) return;
  loadNotesIntoFeed(leadId, objectId);
}

async function deleteNote(noteId, leadId, objectId = null) {
  const ok = await apiDeleteNote(noteId);
  if (!ok) return;
  loadNotesIntoFeed(leadId, objectId);
}

function renderTab(l) {
  if(activeTab==='overview') return renderOverview(l);
  if(activeTab==='msgs') return renderMsgs(l);
  if(activeTab==='calls') return renderCalls(l);
  return '';
}

function getOverviewDisplayData(l) {
  if (!l.has_multiple_objects || !l.objects || !l.objects.length) {
    return { leadId: l.id, objectId: null, data: l, isLead: true };
  }
  const obj = activeObjectId ? l.objects.find(o => o.id === activeObjectId) : null;
  const sel = obj || l.objects[0];
  if (sel && sel.id) activeObjectId = sel.id;
  const data = { ...sel, communication_done: l.communication_done };
  return { leadId: l.id, objectId: sel ? sel.id : null, data, isLead: false };
}

async function updateOverviewField(leadId, objectId, field, value) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  if (field === 'communication_done') {
    const payload = getLeadPayloadForUpdate(l, { [field]: value });
    const updated = await apiUpdateLead(leadId, payload);
    if (updated) { l.communication_done = !!value; showSaveIndicator('cardField-' + leadId + '-communication_done'); updateStats(); }
    return;
  }
  const suffix = objectId != null ? objectId : 'l';
  if (objectId != null) {
    const obj = (l.objects || []).find(o => o.id === objectId);
    if (!obj) return;
    const body = { ...obj, [field]: value };
    const updated = await apiUpdateObject(leadId, objectId, body);
    if (updated) { Object.assign(obj, updated); showSaveIndicator('cardField-' + leadId + '-' + suffix + '-' + field); updateStats(); }
  } else {
    const payload = getLeadPayloadForUpdate(l, { [field]: value });
    const updated = await apiUpdateLead(leadId, payload);
    if (updated) {
      l[field] = value;
      if (field === 'last_contact') l.date = value;
      showSaveIndicator('cardField-' + leadId + '-' + suffix + '-' + field);
      updateStats();
    }
  }
}

// OVERVIEW
const workTypesList = () => (CONFIG.workTypes || []);

function renderOverview(l) {
  const { leadId, objectId, data, isLead } = getOverviewDisplayData(l);
  const si = getStatusInfo(l.status);
  const lastMsg = (l.msgs && l.msgs.length) ? l.msgs[l.msgs.length-1] : null;
  const wtArr = Array.isArray(data.work_types) ? data.work_types : [];
  const workTypesHtml = workTypesList().map(wt => {
    const checked = wtArr.includes(wt);
    const wtEsc = String(wt).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    return `<label class="work-type-cb"><input type="checkbox" ${checked ? 'checked' : ''} onchange="toggleOverviewWorkType(${leadId}, ${objectId || 'null'}, '${wtEsc}', this.checked)"> ${escapeHtml(wt)}</label>`;
  }).join('');
  const budgetOpts = CONFIG.budgets ? Object.entries(CONFIG.budgets).map(([k, v]) => `<option value="${escapeHtml(k)}" ${data.budget === k ? 'selected' : ''}>${escapeHtml(v.label)}</option>`).join('') : '';
  const objectOpts = CONFIG.objectTypes ? CONFIG.objectTypes.map(t => `<option value="${escapeHtml(t)}" ${(data.object_type || data.obj) === t ? 'selected' : ''}>${escapeHtml(t)}</option>`).join('') : '';
  const showDealAmount = l.status === 'client' || l.status === 'repeat';
  const dealAmountFormatted = formatDealAmount(data.deal_amount);
  const dealAmountRowWithId = showDealAmount
    ? `<div class="ai-field" id="cardField-${leadId}-${objectId || 'l'}-deal_amount"><div class="aif-label">Сумма сделки</div><input type="text" class="aif-edit-input" value="${escapeHtml(dealAmountFormatted)}" placeholder="Введите сумму сметы" data-lead-id="${leadId}" data-object-id="${objectId || ''}" oninput="filterDealAmountInput(this)" onblur="saveOverviewDealAmountOnBlur(this)"></div>`
    : '';
  const objSwitcher = (l.has_multiple_objects && l.objects && l.objects.length) ? `
    <div class="overview-object-switcher">
      <div class="rp-sec">Объекты</div>
      <div class="object-tabs">
        ${(l.objects || []).map(o => `<button type="button" class="dbtn object-tab ${(o.id === activeObjectId) ? 'active' : ''}" onclick="selectOverviewObject(${o.id})">${escapeHtml(o.name || 'Объект')}</button>`).join('')}
        <button type="button" class="dbtn object-tab-add" onclick="addOverviewObject(${leadId})">+ Новый</button>
      </div>
    </div>
  ` : '';
  const cardObjectActions = (objectId != null && l.objects && l.objects.length) ? `
    <div class="object-card-actions">
      <div class="ai-field" id="cardField-${leadId}-${objectId}-name"><div class="aif-label">Название объекта</div><input type="text" class="aif-edit-input" value="${escapeHtml(data.name || 'Объект')}" placeholder="Название" onblur="saveObjectNameOnBlur(this, ${leadId}, ${objectId})"></div>
      ${l.objects.length > 1 ? `<button type="button" class="dbtn object-card-delete" onclick="deleteOverviewObject(${leadId}, ${objectId})" title="Удалить объект">Удалить объект</button>` : ''}
    </div>
  ` : '';
  return `
    ${objSwitcher}
    <div class="ai-card lead-card-block">
      <div class="ai-label">КАРТОЧКА ОБЪЕКТА</div>
      ${cardObjectActions}
      <div class="ai-grid">
        <div class="ai-field" id="cardField-${leadId}-${objectId || 'l'}-budget"><div class="aif-label">Бюджет</div><select class="aif-edit-select" onchange="updateOverviewField(${leadId}, ${objectId || 'null'}, 'budget', this.value)">${budgetOpts}</select></div>
        <div class="ai-field" id="cardField-${leadId}-${objectId || 'l'}-object_type"><div class="aif-label">Тип объекта</div><select class="aif-edit-select" onchange="updateOverviewField(${leadId}, ${objectId || 'null'}, 'object_type', this.value)">${objectOpts}</select></div>
        <div class="ai-field" id="cardField-${leadId}-${objectId || 'l'}-address"><div class="aif-label">Адрес</div><input type="text" class="aif-edit-input" value="${escapeHtml(data.address || '')}" placeholder="Адрес" onblur="updateOverviewField(${leadId}, ${objectId || 'null'}, 'address', this.value)"></div>
        <div class="ai-field" id="cardField-${leadId}-last_contact"><div class="aif-label">Последний контакт</div><input type="text" class="aif-edit-input" value="${escapeHtml(l.last_contact || l.date || '')}" placeholder="ГГГГ-ММ-ДД или ДД.ММ.ГГГГ" onblur="saveLastContactOnBlur(this, ${leadId})" title="Меняйте дату, чтобы убрать лид из выбранного периода аналитики"></div>
        ${dealAmountRowWithId}
        <div class="ai-field ai-field-toggle" id="cardField-${leadId}-communication_done">
          <div class="aif-label">Завершил общение</div>
          <label class="toggle-wrap"><input type="checkbox" ${data.communication_done ? 'checked' : ''} onchange="updateOverviewField(${leadId}, null, 'communication_done', this.checked)"><span class="toggle-slider"></span></label>
        </div>
      </div>
      ${lastMsg ? `<div class="ai-comment" style="margin-top:8px">📩 <b>Последнее сообщение:</b> ${escapeHtml(lastMsg.text)}</div>` : ''}
    </div>

    <div class="overview-block overview-desc-block" id="cardField-${leadId}-${objectId || 'l'}-description">
      <div class="overview-block-title">ОПИСАНИЕ ПРОЕКТА</div>
      <textarea class="overview-description-ta" id="descriptionTa-${leadId}-${objectId || 'l'}" placeholder="Добавьте описание проекта или нажмите Обновить" data-lead-id="${leadId}" data-object-id="${objectId || ''}">${escapeHtml(data.description || '')}</textarea>
      <button type="button" class="dbtn" id="btnSummarize-${leadId}" style="margin-top:8px;font-size:9px" onclick="requestLeadSummary(${leadId})">↺ Обновить из переписки и заметок</button>
    </div>

    <div class="overview-block work-types-block" id="cardField-${leadId}-${objectId || 'l'}-work_types">
      <div class="overview-block-title work-types-toggle" onclick="toggleWorkTypesBlock(this)">Виды работ <span class="wt-chevron">▼</span></div>
      <div class="work-types-row work-types-body collapsed">${workTypesHtml}</div>
    </div>

    <div class="notes-feed" data-lead-id="${leadId}" data-object-id="${objectId || ''}">
      <div class="notes-feed-title">📝 Заметки</div>
      <div class="notes-feed-add">
        <input type="text" id="noteInput-${leadId}-${objectId || 'l'}" class="notes-input" placeholder="Текст заметки..." onkeydown="if(event.key==='Enter')addNoteWithObject(${leadId}, ${objectId || 'null'})">
        <button type="button" class="dbtn primary" onclick="addNoteWithObject(${leadId}, ${objectId || 'null'})">Добавить заметку</button>
      </div>
      <div id="notesList-${leadId}-${objectId || 'l'}" class="notes-list">Загрузка...</div>
    </div>

    <div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <div style="font-family:'Unbounded',sans-serif;font-size:11px;font-weight:600">📞 Звонки</div>
        <button class="dbtn" onclick="switchTab('calls')">Все →</button>
      </div>
      ${l.calls.length===0
        ? `<div style="font-size:10px;color:var(--muted);text-align:center;padding:18px;background:var(--surface);border:1px dashed var(--border);border-radius:7px">
            Записей нет. Загрузите аудио — автотранскрибация за 1-2 мин
           </div>`
        : l.calls.slice(0,1).map(c=>`
          <div class="call-item">
            <div class="ci-top">
              <span style="font-size:16px">🎙️</span>
              <div><div style="font-size:11px;font-weight:500">${c.name}</div><div style="font-size:9px;color:var(--muted)">${c.date}</div></div>
              <div class="ci-dur">⏱ ${c.duration}</div>
            </div>
            <div class="transcription">${c.transcription}</div>
            <div class="facts">${c.facts.map(f=>`<div class="fact">✦ ${f}</div>`).join('')}</div>
          </div>`).join('')
      }
    </div>
  `;
}

function toggleWorkTypesBlock(titleEl) {
  const block = titleEl && titleEl.closest('.work-types-block');
  if (!block) return;
  const body = block.querySelector('.work-types-body');
  const chevron = block.querySelector('.wt-chevron');
  if (body) body.classList.toggle('collapsed');
  if (chevron) chevron.textContent = body && body.classList.contains('collapsed') ? '▶' : '▼';
}

function selectOverviewObject(objectId) {
  activeObjectId = objectId;
  saveState();
  const l = leads.find(x => x.id === activeId);
  if (l) { const tb = document.getElementById('tabBody'); if (tb) tb.innerHTML = renderOverview(l); if (activeTab === 'overview') loadNotesIntoFeed(activeId, objectId); }
}

async function addOverviewObject(leadId) {
  const l = leads.find(x => x.id === leadId);
  if (!l || !l.has_multiple_objects) return;
  const n = (l.objects || []).length + 1;
  const created = await apiCreateObject(leadId, { name: 'Объект ' + n });
  if (!created) return;
  if (!l.objects) l.objects = [];
  l.objects.push(created);
  activeObjectId = created.id;
  saveState();
  renderDetail();
  if (activeTab === 'overview') loadNotesIntoFeed(leadId, created.id);
}

async function saveObjectNameOnBlur(inputEl, leadId, objectId) {
  const l = leads.find(x => x.id === leadId);
  const obj = (l && l.objects || []).find(o => o.id === objectId);
  if (!obj || !inputEl) return;
  const name = (inputEl.value || '').trim() || (obj.name || 'Объект');
  if (name === (obj.name || 'Объект')) return;
  const updated = await apiUpdateObject(leadId, objectId, { ...obj, name });
  if (updated) { obj.name = updated.name; showSaveIndicator('cardField-' + leadId + '-' + objectId + '-name'); }
}

async function deleteOverviewObject(leadId, objectId) {
  if (!confirm('Удалить этот объект? Заметки объекта останутся без привязки.')) return;
  const ok = await apiDeleteObject(leadId, objectId);
  if (!ok) return;
  const l = leads.find(x => x.id === leadId);
  if (l && l.objects) {
    l.objects = l.objects.filter(o => o.id !== objectId);
    if (activeObjectId === objectId) activeObjectId = (l.objects[0] && l.objects[0].id) || null;
    saveState();
    renderDetail();
    if (activeTab === 'overview') loadNotesIntoFeed(leadId, activeObjectId);
  }
}

async function toggleOverviewWorkType(leadId, objectId, workTypeName, checked) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const data = objectId != null ? (l.objects || []).find(o => o.id === objectId) : l;
  if (!data) return;
  let arr = Array.isArray(data.work_types) ? [...data.work_types] : [];
  if (checked) { if (!arr.includes(workTypeName)) arr.push(workTypeName); }
  else arr = arr.filter(x => x !== workTypeName);
  await updateOverviewField(leadId, objectId, 'work_types', arr);
}

async function saveOverviewDealAmountOnBlur(inputEl) {
  const leadId = parseInt(inputEl.getAttribute('data-lead-id'), 10);
  const oid = inputEl.getAttribute('data-object-id');
  const objectId = oid === '' || oid === 'null' ? null : parseInt(oid, 10);
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  const digits = (inputEl.value || '').replace(/\D/g, '');
  const value = digits ? parseInt(digits, 10) : null;
  await updateOverviewField(leadId, objectId, 'deal_amount', value);
  updateStats();
}

function addNoteWithObject(leadId, objectId) {
  const id = objectId === 'null' || objectId == null ? null : objectId;
  const input = document.getElementById('noteInput-' + leadId + '-' + (id || 'l'));
  const text = (input && input.value || '').trim();
  if (!text) return;
  addNote(leadId, text, id);
  if (input) input.value = '';
}

// MESSAGES
const MESSAGE_SOURCES = ['Авито', 'Телеграм', 'WhatsApp', 'Телефон'];

function renderMsgs(l) {
  const leadId = l.id;
  const sourcesOpts = (CONFIG.messageSources || MESSAGE_SOURCES).map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
  return `
    <div id="messagesList-${leadId}" class="msg-thread messages-feed">Загрузка...</div>
    <div class="msg-form-tabs">
      <div class="msg-form-panel active" data-msg-panel="write">
        <div class="msg-form-row">
          <textarea id="msgText-${leadId}" class="msg-form-text" placeholder="Текст сообщения..." rows="2"></textarea>
        </div>
        <div class="msg-form-row">
          <select id="msgSource-write-${leadId}" class="msg-form-select">${sourcesOpts}</select>
          <button type="button" class="dbtn" onclick="sendMessageAs(${leadId}, 'in')">← Входящее</button>
          <button type="button" class="dbtn primary" onclick="sendMessageAs(${leadId}, 'out')">Исходящее →</button>
          <button type="button" id="msgAiBtn-${leadId}" class="dbtn" onclick="requestAiReply(${leadId})">✦ AI ответ</button>
        </div>
      </div>
      <div class="msg-form-panel" data-msg-panel="paste">
        <textarea id="msgPaste-${leadId}" class="msg-form-paste" placeholder="Вставьте переписку из Авито (строки с временем 14:21 или датой 19 декабря 2025 г. — разделители)..." rows="8"></textarea>
        <div class="msg-form-row">
          <select id="msgSource-paste-${leadId}" class="msg-form-select">${sourcesOpts}</select>
          <button type="button" class="dbtn primary" onclick="importAvitoText(${leadId})">Импортировать</button>
        </div>
      </div>
      <div class="msg-form-panel" data-msg-panel="telegram">
        <div class="msg-telegram-drop" id="msgTelegramDrop-${leadId}"
             onclick="document.getElementById('msgTelegramFile-${leadId}').click()"
             ondragover="event.preventDefault();this.classList.add('drag')"
             ondragleave="this.classList.remove('drag')"
             ondrop="handleTelegramDrop(event, ${leadId})">
          <input type="file" id="msgTelegramFile-${leadId}" accept=".html" class="msg-form-file" onchange="onTelegramFileSelected(${leadId}, this)">
          <label for="msgTelegramFile-${leadId}" class="dbtn" onclick="event.stopPropagation()">Выбрать .html файл</label>
          <span class="msg-telegram-drop-text">или перетащите файл сюда</span>
        </div>
        <div id="msgTelegramPreview-${leadId}" class="msg-telegram-preview" style="display:none">
          <div class="msg-telegram-preview-body" id="msgTelegramPreviewBody-${leadId}"></div>
          <button type="button" class="dbtn primary" onclick="doImportTelegramFromPreview(${leadId})">Импортировать</button>
        </div>
      </div>
      <div class="msg-form-tab-icons">
        <button type="button" class="msg-form-tab-icon active" data-msg-tab="write" title="Написать">✏️</button>
        <button type="button" class="msg-form-tab-icon" data-msg-tab="paste" title="Вставить текст">📋</button>
        <button type="button" class="msg-form-tab-icon" data-msg-tab="telegram" title="Загрузить Телеграм">📁</button>
      </div>
    </div>
  `;
}

function initMsgFormTabs() {
  document.querySelectorAll('.msg-form-tab-icon').forEach(tab => {
    tab.addEventListener('click', () => {
      const name = tab.dataset.msgTab;
      document.querySelectorAll('.msg-form-tab-icon').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.msg-form-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = document.querySelector('.msg-form-panel[data-msg-panel="' + name + '"]');
      if (panel) panel.classList.add('active');
    });
  });
}

async function loadMessagesIntoFeed(leadId) {
  const el = document.getElementById('messagesList-' + leadId);
  if (!el) return;
  el.classList.add('messages-feed');
  const list = await apiGetMessages(leadId);
  if (list === null) { el.textContent = 'Ошибка загрузки'; return; }
  if (!list.length) {
    el.innerHTML = '<div class="messages-empty">Переписки пока нет</div>';
    initMsgFormTabs();
    return;
  }
  el.innerHTML = list.map(m => renderMessageItem(m, leadId)).join('');
  el.scrollTop = el.scrollHeight;
  initMsgFormTabs();
}

function renderMessageItem(m, leadId) {
  const dt = formatMessageDate(m.created_at);
  const dir = m.direction || 'unknown';
  const isOut = dir === 'out';
  const isIn = dir === 'in';
  const isUnknown = dir === 'unknown';
  let bubbleClass = 'msg-bubble';
  if (isOut) bubbleClass += ' msg-bubble-out';
  else if (isIn) bubbleClass += ' msg-bubble-in';
  else bubbleClass += ' msg-bubble-unknown';
  let alignClass = 'msg-row';
  if (isOut) alignClass += ' msg-row-out';
  else if (isIn) alignClass += ' msg-row-in';
  else alignClass += ' msg-row-unknown';
  const dirButtons = isUnknown
    ? `<span class="msg-dir-btns">
         <button type="button" class="msg-dir-btn" onclick="setMessageDirection(${m.id}, ${leadId}, 'in')" title="Клиент">← клиент</button>
         <button type="button" class="msg-dir-btn" onclick="setMessageDirection(${m.id}, ${leadId}, 'out')" title="Я">я →</button>
       </span>`
    : '';
  return `<div class="${alignClass}" data-msg-id="${m.id}">
    <div class="${bubbleClass}">
      <div class="msg-text">${escapeHtml(m.text)}</div>
      ${dirButtons}
      <div class="msg-meta">${escapeHtml(m.source)} · ${escapeHtml(dt)}</div>
      <button type="button" class="msg-delete" onclick="deleteMessage(${m.id}, ${leadId})" title="Удалить">×</button>
    </div>
  </div>`;
}

function formatMessageDate(createdAt) {
  if (!createdAt) return '—';
  const s = String(createdAt);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}`;
  return s;
}

async function setMessageDirection(msgId, leadId, direction) {
  const updated = await apiUpdateMessageDirection(msgId, direction);
  if (!updated) return;
  loadMessagesIntoFeed(leadId);
}

async function deleteMessage(msgId, leadId) {
  const ok = await apiDeleteMessage(msgId);
  if (!ok) return;
  loadMessagesIntoFeed(leadId);
}

async function sendMessageAs(leadId, direction) {
  const input = document.getElementById('msgText-' + leadId);
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  const sourceEl = document.getElementById('msgSource-write-' + leadId);
  const source = sourceEl ? sourceEl.value : 'Авито';
  const created = await apiCreateMessage(leadId, { text, direction, source });
  if (!created) return;
  input.value = '';
  if ((direction || '').toLowerCase() === 'in') {
    const l = leads.find(x => x.id === leadId);
    if (l) l.communication_done = false;
    updateStats();
    const cb = document.querySelector('#cardField-' + leadId + '-communication_done input[type=checkbox]');
    if (cb) cb.checked = false;
  }
  await loadMessagesIntoFeed(leadId);
  const listEl = document.getElementById('messagesList-' + leadId);
  if (listEl) listEl.scrollTop = listEl.scrollHeight;
}

async function requestAiReply(leadId) {
  const btn = document.getElementById('msgAiBtn-' + leadId);
  const api = typeof window !== 'undefined' && window.apiGenerateReply;
  if (!api) return;
  if (btn) { btn.disabled = true; btn.textContent = 'Генерирую...'; }
  try {
    const data = await api(leadId);
    const ta = document.getElementById('msgText-' + leadId);
    if (ta && data && data.reply != null) ta.value = data.reply;
  } catch (e) {
    alert(e && (e.message || String(e)) || 'Ошибка генерации ответа');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '✦ AI ответ'; }
  }
}

function parseAvitoPaste(text) {
  const lines = text.split(/\r?\n/);
  const messages = [];
  let currentTime = '';
  let currentDate = '';
  const timeRe = /^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$/;
  const dateRe = /^\s*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})\s+г\.?\s*$/i;
  const months = { января:1, февраля:2, марта:3, апреля:4, мая:5, июня:6, июля:7, августа:8, сентября:9, октября:10, ноября:11, декабря:12 };
  let buffer = [];
  function flush() {
    if (buffer.length) {
      const text = buffer.join('\n').trim();
      if (text) {
        let created_at = '';
        if (currentDate && currentTime) created_at = currentDate + ' ' + currentTime + ':00';
        else if (currentTime) {
          const d = new Date();
          created_at = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0') + ' ' + currentTime + ':00';
        }
        messages.push({ text, direction: 'unknown', source: '', created_at: created_at || null });
      }
      buffer = [];
    }
  }
  for (const line of lines) {
    const timeMatch = line.match(timeRe);
    const dateMatch = line.match(dateRe);
    if (dateMatch) {
      flush();
      const [, day, monthName, year] = dateMatch;
      const month = months[monthName.toLowerCase()];
      if (month) currentDate = year + '-' + String(month).padStart(2, '0') + '-' + String(parseInt(day, 10)).padStart(2, '0');
    } else if (timeMatch) {
      flush();
      const [, h, m, s] = timeMatch;
      currentTime = h.padStart(2, '0') + ':' + m.padStart(2, '0') + (s ? ':' + s.padStart(2, '0') : '');
    } else {
      buffer.push(line);
    }
  }
  flush();
  return messages;
}

async function importAvitoText(leadId) {
  const textarea = document.getElementById('msgPaste-' + leadId);
  const sourceEl = document.getElementById('msgSource-paste-' + leadId);
  if (!textarea) return;
  const text = textarea.value.trim();
  if (!text) return;
  const source = sourceEl ? sourceEl.value : 'Авито';
  const messages = parseAvitoPaste(text);
  if (!messages.length) return;
  const withSource = messages.map(m => ({ ...m, source }));
  const list = await apiCreateMessagesBulk(leadId, withSource);
  if (!list) return;
  await refreshLeadAfterBulkMessages(leadId);
  textarea.value = '';
  await loadMessagesIntoFeed(leadId);
  const listEl = document.getElementById('messagesList-' + leadId);
  if (listEl) listEl.scrollTop = listEl.scrollHeight;
}

let lastTelegramMessagesByLead = {};

function parseTelegramHtml(htmlString) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlString, 'text/html');
  const me = (CONFIG.telegram_username || '').toString().trim().toLowerCase();
  const rows = doc.querySelectorAll('div.message.default');
  const messages = [];
  const uniqueNames = new Set();
  const nameCounts = {};
  let lastSender = '';
  for (const row of rows) {
    const fromEl = row.querySelector('div.from_name');
    let fromNameRaw;
    if (fromEl) {
      fromNameRaw = (fromEl.textContent || '');
      lastSender = fromNameRaw;
      if (fromNameRaw !== '') uniqueNames.add(fromNameRaw);
    } else {
      fromNameRaw = lastSender;
    }
    if (fromNameRaw !== '') nameCounts[fromNameRaw] = (nameCounts[fromNameRaw] || 0) + 1;
    const fromName = fromNameRaw.trim();
    const direction = me && fromName && fromName.toLowerCase() === me ? 'out' : 'in';
    const dateEl = row.querySelector('div.pull_right.date');
    const title = dateEl ? (dateEl.getAttribute('title') || '').trim() : '';
    let created_at = '';
    if (title) {
      const m = title.match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2}:\d{2})/);
      if (m) created_at = m[3] + '-' + m[2] + '-' + m[1] + ' ' + m[4];
    }
    let text = '';
    const textEl = row.querySelector('div.text');
    if (textEl) {
      const html = textEl.innerHTML || '';
      const withNewlines = html.replace(/<br\s*\/?>/gi, '\n');
      const div = doc.createElement('div');
      div.innerHTML = withNewlines;
      text = (div.textContent || '').trim();
    }
    if (!text) {
      const mediaWrap = row.querySelector('div.media_wrap');
      const oggLink = row.querySelector('a[href*=".ogg"]');
      if (oggLink) text = '[Голосовое сообщение]';
      else if (mediaWrap) text = '[Фото]';
    }
    messages.push({ text: text || '[Сообщение]', direction, source: 'Телеграм', created_at: created_at || null });
  }
  return { messages, uniqueNames: [...uniqueNames].sort(), nameCounts };
}

function handleTelegramDrop(e, leadId) {
  e.preventDefault();
  e.currentTarget.classList.remove('drag');
  const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (file && file.name.toLowerCase().endsWith('.html')) handleTelegramFile(leadId, file);
}

async function onTelegramFileSelected(leadId, fileInput) {
  const file = fileInput && fileInput.files && fileInput.files[0];
  if (!file || !file.name.toLowerCase().endsWith('.html')) {
    const previewWrap = document.getElementById('msgTelegramPreview-' + leadId);
    if (previewWrap) previewWrap.style.display = 'none';
    lastTelegramMessagesByLead[leadId] = [];
    return;
  }
  await handleTelegramFile(leadId, file);
}

async function handleTelegramFile(leadId, file) {
  const previewWrap = document.getElementById('msgTelegramPreview-' + leadId);
  const previewBody = document.getElementById('msgTelegramPreviewBody-' + leadId);
  const html = await new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsText(file, 'UTF-8');
  });
  let result;
  try {
    result = parseTelegramHtml(html);
  } catch (e) {
    console.error('Telegram HTML parse error', e);
    if (previewWrap) previewWrap.style.display = 'none';
    return;
  }
  const { messages, uniqueNames, nameCounts } = result;
  lastTelegramMessagesByLead[leadId] = messages;
  if (previewWrap && previewBody) {
    const n = messages.length;
    const configName = (CONFIG.telegram_username || '').toString();
    const me = configName.trim().toLowerCase();
    const matchFound = me && uniqueNames.some(function (raw) { return raw.trim().toLowerCase() === me; });
    const lines = [
      'Найдено сообщений: ' + n,
      'Участники чата:',
      ...uniqueNames.map(function (name) { return '- ' + name + ' (' + (nameCounts[name] || 0) + ' сообщений)'; }),
      'Твоё имя в CONFIG.telegram_username: "' + configName + '"',
      'Совпадение найдено: ' + (matchFound ? 'ДА' : 'НЕТ')
    ];
    previewBody.textContent = lines.join('\n');
    previewWrap.style.display = 'block';
  }
}

async function refreshLeadAfterBulkMessages(leadId) {
  const updated = await apiGetLead(leadId);
  if (updated) {
    const l = leads.find(x => x.id === leadId);
    if (l) Object.assign(l, updated);
    updateStats();
    const cb = document.querySelector('#cardField-' + leadId + '-communication_done input[type=checkbox]');
    if (cb) cb.checked = !!updated.communication_done;
  }
}

async function doImportTelegramFromPreview(leadId) {
  const messages = lastTelegramMessagesByLead[leadId];
  if (!messages || !messages.length) return;
  const list = await apiCreateMessagesBulk(leadId, messages);
  if (!list) return;
  await refreshLeadAfterBulkMessages(leadId);
  lastTelegramMessagesByLead[leadId] = [];
  const previewWrap = document.getElementById('msgTelegramPreview-' + leadId);
  if (previewWrap) previewWrap.style.display = 'none';
  const fileInput = document.getElementById('msgTelegramFile-' + leadId);
  if (fileInput) fileInput.value = '';
  await loadMessagesIntoFeed(leadId);
  const listEl = document.getElementById('messagesList-' + leadId);
  if (listEl) listEl.scrollTop = listEl.scrollHeight;
}

// CALLS
function renderCalls(l) {
  return `
    <div class="upload-zone" onclick="document.getElementById('fi-${l.id}').click()"
         ondragover="event.preventDefault();this.classList.add('drag')"
         ondragleave="this.classList.remove('drag')"
         ondrop="handleDrop(event,${l.id})">
      <input type="file" id="fi-${l.id}" accept="audio/*,.mp3,.m4a,.ogg,.wav,.aac" onchange="handleUpload(event,${l.id})">
      <div class="uz-icon">🎙️</div>
      <div class="uz-text"><b>Нажмите или перетащите</b> запись звонка<br>mp3, m4a, ogg, wav — Whisper транскрибирует за 1–2 мин</div>
    </div>
    <div id="callsContainer-${l.id}">
      ${l.calls.length===0
        ? `<div style="font-size:10px;color:var(--muted);text-align:center;padding:14px">Записей нет</div>`
        : l.calls.map(c=>`
          <div class="call-item">
            <div class="ci-top">
              <span style="font-size:16px">🎙️</span>
              <div><div style="font-size:11px;font-weight:500">${c.name}</div><div style="font-size:9px;color:var(--muted)">${c.date}</div></div>
              <div class="ci-dur">⏱ ${c.duration}</div>
            </div>
            <div class="transcription">${c.transcription}</div>
            <div class="facts">${c.facts.map(f=>`<div class="fact">✦ ${f}</div>`).join('')}</div>
          </div>`).join('')
      }
    </div>
  `;
}

// UPLOAD
function handleDrop(e,id){e.preventDefault();e.currentTarget.classList.remove('drag');simulateUpload(id,e.dataTransfer.files[0]?.name||'звонок.mp3');}
function handleUpload(e,id){const f=e.target.files[0];if(f)simulateUpload(id,f.name);}
function simulateUpload(id,fname) {
  const cont = document.getElementById(`callsContainer-${id}`);
  if(!cont) return;
  const up = document.createElement('div');
  up.className='uploading fade-in';
  up.innerHTML=`<span style="font-size:18px">🎙️</span><div class="prog-wrap"><div class="prog-label">Транскрибирую «${fname}» через Whisper...</div><div class="prog-bar"><div class="prog-fill"></div></div></div>`;
  cont.prepend(up);
  setTimeout(()=>{
    up.remove();
    const l=leads.find(x=>x.id===id);
    l.calls.push({
      name:fname.replace(/\.[^.]+$/,''),date:'только что',duration:'7:33',
      transcription:'Клиент: Добрый день, вы звонили по поводу замера? Мастер: Да, хотел уточнить детали. Когда удобно? Клиент: В четверг с 12 до 15. Мастер: Договорились, запишу. Адрес тот же? Клиент: Да.',
      facts:['Замер в четверг 12–15','Адрес подтверждён','Звонок состоялся'],
    });
    renderDetail();
  },3000);
}

function injectStatusOptionStyles() {
  if (!CONFIG.statuses) return;
  const id = 'status-option-hover-styles';
  if (document.getElementById(id)) return;
  const style = document.createElement('style');
  style.id = id;
  style.textContent = Object.entries(CONFIG.statuses).map(([k, cfg]) => {
    const bg = (cfg && cfg.bg) || 'var(--border)';
    return `.aif-edit-select option[data-status="${k}"]:hover { background: ${bg} !important; }`;
  }).join('\n');
  document.head.appendChild(style);
}

// INIT
async function init() {
  injectStatusOptionStyles();
  document.addEventListener('click', function periodSwitcherClick(e) {
    const btn = e.target.closest('#periodSwitcher .period-btn');
    if (btn) setPeriod(btn.getAttribute('data-period'));
  });
  loadState();
  const raw = await apiGetLeads();
  leads = (raw || []).map(mapLeadFromApi);
  setPeriod(currentPeriod);
  setFilter(currentFilter);
  if (activeId != null && leads.some(l => l.id === activeId)) {
    renderDetail();
  } else if (leads.length) {
    openLead(leads[0].id);
  }
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
