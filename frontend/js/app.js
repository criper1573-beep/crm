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

function getLeadPayloadForUpdate(l, overrides = {}) {
  return {
    name: l.name,
    phone: l.phone || '',
    avito_link: l.avito_link ?? l.link ?? '',
    address: l.address || '',
    object_type: l.object_type ?? l.obj ?? '',
    budget: l.budget,
    status: l.status,
    last_contact: l.last_contact ?? l.date ?? '',
    comment: l.comment || '',
    work_types: Array.isArray(l.work_types) ? l.work_types : (l.work_types ? JSON.parse(l.work_types || '[]') : []),
    description: l.description ?? '',
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
  renderDetail();
  renderList();
  updateStats();
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
let activeId = null;
let activeTab = 'overview';
let currentFilter = 'all';

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
  const groups = {hot:0,client:0,repeat:0,drain:0,sql:0};
  leads.forEach(l => { const g = getStatusGroup(l.status); if(groups[g]!==undefined) groups[g]++; });
  document.getElementById('cntHot').textContent = groups.hot;
  document.getElementById('cntClient').textContent = groups.client;
  document.getElementById('cntAll').textContent = leads.length;
  document.getElementById('s1').textContent = groups.hot;
  document.getElementById('s2').textContent = groups.client;
  document.getElementById('s3').textContent = groups.repeat + groups.sql;
  document.getElementById('s4').textContent = groups.drain;

  // funnel
  const fl = document.getElementById('funnelList');
  fl.innerHTML = funnelConfig.map(f => {
    const cnt = leads.filter(l => getStatusGroup(l.status) === f.key).length;
    const pct = leads.length ? Math.round(cnt/leads.length*100) : 0;
    return `<div class="funnel-item" onclick="setFilter('${f.key}',null)">
      <div class="fi-dot" style="background:${f.color}"></div>
      <div class="fi-label">${f.label}</div>
      <div class="fi-count">${cnt}</div>
      <div class="fi-pct" style="color:${f.color}">${pct}%</div>
    </div>`;
  }).join('');

  // budget bars
  const budgets = {lo:0,mid:0,hi:0};
  leads.forEach(l => { if(budgets[l.budget]!==undefined) budgets[l.budget]++; });
  document.getElementById('budgetBars').innerHTML = [
    {k:'hi',label:'> 100к',color:'var(--accent2)'},
    {k:'mid',label:'30–100к',color:'var(--accent)'},
    {k:'lo',label:'< 30к',color:'var(--muted)'},
  ].map(b => {
    const pct = leads.length ? Math.round(budgets[b.k]/leads.length*100) : 0;
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

  // alerts — hot with old date or no comment
  const alerts = leads.filter(l => getStatusGroup(l.status)==='hot' && (!l.comment || l.comment===''));
  const noReply = leads.filter(l => getStatusGroup(l.status)==='hot' && (l.msgs && l.msgs.length > 0 && !l.msgs[l.msgs.length-1].out));
  document.getElementById('alertsList').innerHTML = [
    ...noReply.slice(0,3).map(l => `
      <div class="alert-item" onclick="openLead(${l.id})">
        <div class="ai-top"><span>${l.name}</span><span style="font-size:8px;color:var(--muted)">${l.date}</span></div>
        <div class="ai-sub">Клиент написал — нет ответа</div>
      </div>`),
    ...leads.filter(l=>l.status==='sql').slice(0,2).map(l => `
      <div class="alert-item warn" onclick="openLead(${l.id})">
        <div class="ai-top"><span>${l.name}</span><span style="font-size:8px;color:var(--muted)">${l.date}</span></div>
        <div class="ai-sub">${l.comment || 'SQL — требует follow-up'}</div>
      </div>`)
  ].join('') || '<div style="font-size:10px;color:var(--muted);text-align:center;padding:10px">Всё обработано 👍</div>';
}

// ─── RENDER LIST ───────────────────────────────────────────
function renderList() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const filtered = leads.filter(l => {
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

function renderFilterRow() {
  const el = document.getElementById('filterRow');
  if (!el || !CONFIG.statuses) return;
  const allBtn = `<button class="ftab active" data-f="all" onclick="setFilter('all',this)">Все</button>`;
  const statusBtns = Object.entries(CONFIG.statuses).map(([key, cfg]) => {
    const color = (cfg && cfg.color) || 'var(--text2)';
    return `<button class="ftab" data-f="${escapeHtml(key)}" onclick="setFilter('${escapeHtml(key)}',this)" style="border-color:${color};color:${color}">${escapeHtml(cfg.label)}</button>`;
  }).join('');
  el.innerHTML = allBtn + statusBtns;
}

function setFilter(f, btn) {
  currentFilter = f;
  document.querySelectorAll('.ftab').forEach(b => b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  else {
    document.querySelectorAll('.ftab').forEach(b => { if(b.dataset.f===f) b.classList.add('active'); });
  }
  renderList();
}

function filterLeads() { renderList(); }

// ─── OPEN LEAD ─────────────────────────────────────────────
function openLead(id) {
  activeId = id;
  activeTab = 'overview';
  renderList();
  renderDetail();
}

function renderDetail() {
  const l = leads.find(x => x.id === activeId);
  if(!l) return;
  const si = getStatusInfo(l.status);
  const bi = BUDGET[l.budget];
  const detail = document.getElementById('detail');

  detail.innerHTML = `
    <div class="detail-header fade-in">
      <div class="d-avatar">${l.name[0]}</div>
      <div>
        <div class="d-name">${l.name}</div>
        <div class="d-sub">
          ${l.address ? `<span>📍 ${l.address}</span>` : ''}
          ${l.phone ? `<span>📞 ${l.phone}</span>` : ''}
          <span class="sbadge ${si.cls}">${si.label}</span>
          ${bi ? `<span class="btag ${bi.cls}">${bi.label}</span>` : ''}
          ${l.obj ? `<span class="otag">${l.obj}</span>` : ''}
          <span style="color:var(--muted);font-size:9px">${l.date}</span>
        </div>
      </div>
      <div class="d-actions">
        ${l.phone ? `<button class="dbtn">📞 ${l.phone}</button>` : ''}
        <a href="${l.link}" target="_blank" style="text-decoration:none"><button class="dbtn">🔗 Авито</button></a>
        <div class="status-dropdown" id="statusDropdown">
          <button type="button" class="dbtn" onclick="toggleStatusDropdown(event)">${si.label} ▼</button>
          <div class="status-dropdown-menu" id="statusDropdownMenu">
            ${Object.entries(CONFIG.statuses).map(([k, v]) => `<button type="button" class="status-dropdown-item" data-status="${k}" style="color:${v.color};--status-bg:${v.bg}" onclick="selectStatus(${l.id}, '${k}', event)"><span class="status-dropdown-dot" style="background:${v.color}"></span>${v.label}</button>`).join('')}
          </div>
        </div>
        <button class="dbtn primary" onclick="switchTab('msgs')">💬 Ответить</button>
        <button type="button" class="dbtn" onclick="deleteLead(${l.id})" style="color:var(--hot);border-color:rgba(255,77,109,0.5)">Удалить лид</button>
      </div>
    </div>
    <div class="dtabs">
      <div class="dtab ${activeTab==='overview'?'active':''}" onclick="switchTab('overview')">🗂 Обзор</div>
      <div class="dtab ${activeTab==='msgs'?'active':''}" onclick="switchTab('msgs')">💬 Переписка</div>
      <div class="dtab ${activeTab==='calls'?'active':''}" onclick="switchTab('calls')">📞 Звонки (${l.calls.length})</div>
    </div>
    <div class="tab-body fade-in" id="tabBody">${renderTab(l)}</div>
  `;
  if (activeTab === 'overview') setTimeout(() => loadNotesIntoFeed(activeId), 0);
  if (activeTab === 'msgs') setTimeout(() => loadMessagesIntoFeed(activeId), 0);
}

function switchTab(tab) {
  activeTab = tab;
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
  if (tab === 'overview') loadNotesIntoFeed(activeId);
  if (tab === 'msgs') setTimeout(() => loadMessagesIntoFeed(activeId), 0);
}

async function loadLastContactFromMessages(leadId) {
  const el = document.getElementById('lastContactDisplay-' + leadId);
  if (!el) return;
  const messages = await apiGetMessages(leadId);
  if (messages && messages.length > 0) {
    const maxDate = messages.reduce((max, m) => {
      const d = m.created_at || '';
      return d > max ? d : max;
    }, '');
    if (maxDate) el.textContent = formatNoteDate(maxDate);
  }
}

function initDescriptionBlur(leadId) {
  const ta = document.getElementById('descriptionTa-' + leadId);
  if (!ta || ta.dataset.blurInited) return;
  ta.dataset.blurInited = '1';
  ta.addEventListener('blur', async function onBlur() {
    const l = leads.find(x => x.id === leadId);
    if (!l) return;
    const value = ta.value.trim();
    if (String(l.description || '') === value) return;
    const payload = getLeadPayloadForUpdate(l, { description: value });
    const updated = await apiUpdateLead(leadId, payload);
    if (updated) l.description = value;
  });
}

async function toggleWorkType(leadId, workTypeName, checked) {
  const l = leads.find(x => x.id === leadId);
  if (!l) return;
  let arr = Array.isArray(l.work_types) ? [...l.work_types] : [];
  if (checked) { if (!arr.includes(workTypeName)) arr.push(workTypeName); }
  else arr = arr.filter(x => x !== workTypeName);
  const payload = getLeadPayloadForUpdate(l, { work_types: arr });
  const updated = await apiUpdateLead(leadId, payload);
  if (updated) l.work_types = arr;
}

async function loadNotesIntoFeed(leadId) {
  loadLastContactFromMessages(leadId);
  initDescriptionBlur(leadId);
  const el = document.getElementById('notesList-' + leadId);
  if (!el) return;
  const notes = await apiGetNotes(leadId);
  if (notes === null) { el.textContent = 'Ошибка загрузки'; return; }
  if (!notes.length) { el.innerHTML = '<div class="notes-empty">Нет заметок</div>'; return; }
  el.innerHTML = notes.map(n => {
    const dt = formatNoteDate(n.created_at);
    return `<div class="note-item" data-note-id="${n.id}">
      <span class="note-date">${escapeHtml(dt)}</span>
      <span class="note-text">${escapeHtml(n.text)}</span>
      <button type="button" class="note-delete" onclick="deleteNote(${n.id}, ${leadId})" title="Удалить">×</button>
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

async function addNote(leadId) {
  const input = document.getElementById('noteInput-' + leadId);
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  const created = await apiCreateNote(leadId, text);
  if (!created) return;
  input.value = '';
  loadNotesIntoFeed(leadId);
}

async function deleteNote(noteId, leadId) {
  const ok = await apiDeleteNote(noteId);
  if (!ok) return;
  loadNotesIntoFeed(leadId);
}

function renderTab(l) {
  if(activeTab==='overview') return renderOverview(l);
  if(activeTab==='msgs') return renderMsgs(l);
  if(activeTab==='calls') return renderCalls(l);
  return '';
}

// OVERVIEW
const workTypesList = () => (CONFIG.workTypes || []);

function renderOverview(l) {
  const si = getStatusInfo(l.status);
  const bi = BUDGET[l.budget];
  const lastMsg = (l.msgs && l.msgs.length) ? l.msgs[l.msgs.length-1] : null;
  const tone = getStatusGroup(l.status)==='hot' ? 'Горячий, готов к сотрудничеству' :
               getStatusGroup(l.status)==='client' ? 'Клиент, договорённость достигнута' :
               getStatusGroup(l.status)==='drain' ? 'Слив — не конвертировался' :
               getStatusGroup(l.status)==='repeat' ? 'Повторный клиент — лояльный' : 'SQL — ждёт финального решения';
  const wtArr = Array.isArray(l.work_types) ? l.work_types : [];
  const workTypesHtml = workTypesList().map(wt => {
    const checked = wtArr.includes(wt);
    const wtEsc = String(wt).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    return `<label class="work-type-cb"><input type="checkbox" ${checked ? 'checked' : ''} onchange="toggleWorkType(${l.id}, '${wtEsc}', this.checked)"> ${escapeHtml(wt)}</label>`;
  }).join('');

  return `
    <div class="ai-card">
      <div class="ai-label"><span class="ai-spin">✦</span> AI-РЕЗЮМЕ ЛИДА · авто из переписки</div>
      <div class="ai-grid">
        <div class="ai-field"><div class="aif-label">Статус</div><div class="aif-val ${getStatusGroup(l.status)==='hot'?'hot':getStatusGroup(l.status)==='client'?'ok':''}">${si.label}</div></div>
        <div class="ai-field"><div class="aif-label">Тип объекта</div><div class="aif-val">${l.obj||'Не указан'}</div></div>
        <div class="ai-field"><div class="aif-label">Бюджет</div><div class="aif-val accent">${bi?bi.label:'Не указан'}</div></div>
        <div class="ai-field"><div class="aif-label">Адрес</div><div class="aif-val">${l.address||'Не указан'}</div></div>
        <div class="ai-field"><div class="aif-label">Последний контакт</div><div class="aif-val" id="lastContactDisplay-${l.id}">${l.date||'—'}</div></div>
        <div class="ai-field"><div class="aif-label">Тон клиента</div><div class="aif-val">${tone}</div></div>
      </div>
      ${lastMsg ? `<div class="ai-comment" style="margin-top:8px">📩 <b>Последнее сообщение:</b> ${escapeHtml(lastMsg.text)}</div>` : ''}
      <button class="dbtn" style="margin-top:10px;font-size:9px" onclick="alert('AI-функция будет добавлена позже')">↺ Обновить из переписки</button>
    </div>

    <div class="overview-block">
      <div class="overview-block-title">Виды работ</div>
      <div class="work-types-row">${workTypesHtml}</div>
    </div>

    <div class="overview-block">
      <div class="overview-block-title">Текстовое описание проекта</div>
      <textarea class="overview-description-ta" id="descriptionTa-${l.id}" placeholder="Описание проекта..." data-lead-id="${l.id}">${escapeHtml(l.description || '')}</textarea>
    </div>

    <div class="notes-feed">
      <div class="notes-feed-title">📝 Заметки</div>
      <div class="notes-feed-add">
        <input type="text" id="noteInput-${l.id}" class="notes-input" placeholder="Текст заметки..." onkeydown="if(event.key==='Enter')addNote(${l.id})">
        <button type="button" class="dbtn primary" onclick="addNote(${l.id})">Добавить заметку</button>
      </div>
      <div id="notesList-${l.id}" class="notes-list">Загрузка...</div>
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

// MESSAGES
const MESSAGE_SOURCES = ['Авито', 'Телеграм', 'WhatsApp', 'Телефон'];

function renderMsgs(l) {
  const leadId = l.id;
  const sourcesOpts = (CONFIG.messageSources || MESSAGE_SOURCES).map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
  return `
    <div id="messagesList-${leadId}" class="msg-thread messages-feed">Загрузка...</div>
    <div class="msg-form-tabs">
      <div class="msg-form-tab-row">
        <button type="button" class="msg-form-tab active" data-msg-tab="write">Написать</button>
        <button type="button" class="msg-form-tab" data-msg-tab="paste">Вставить текст</button>
        <button type="button" class="msg-form-tab" data-msg-tab="telegram">Загрузить Телеграм</button>
      </div>
      <div class="msg-form-panel active" data-msg-panel="write">
        <div class="msg-form-row">
          <textarea id="msgText-${leadId}" class="msg-form-text" placeholder="Текст сообщения..." rows="2"></textarea>
        </div>
        <div class="msg-form-row">
          <select id="msgSource-write-${leadId}" class="msg-form-select">${sourcesOpts}</select>
          <button type="button" class="dbtn" onclick="sendMessageAs(${leadId}, 'in')">← Входящее</button>
          <button type="button" class="dbtn primary" onclick="sendMessageAs(${leadId}, 'out')">Исходящее →</button>
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
    </div>
  `;
}

function initMsgFormTabs() {
  document.querySelectorAll('.msg-form-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const name = tab.dataset.msgTab;
      document.querySelectorAll('.msg-form-tab').forEach(t => t.classList.remove('active'));
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
  await loadMessagesIntoFeed(leadId);
  const listEl = document.getElementById('messagesList-' + leadId);
  if (listEl) listEl.scrollTop = listEl.scrollHeight;
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

async function doImportTelegramFromPreview(leadId) {
  const messages = lastTelegramMessagesByLead[leadId];
  if (!messages || !messages.length) return;
  const list = await apiCreateMessagesBulk(leadId, messages);
  if (!list) return;
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

// INIT
async function init() {
  renderFilterRow();
  const raw = await apiGetLeads();
  leads = (raw || []).map(mapLeadFromApi);
  updateStats();
  renderList();
  if (leads.length) setTimeout(() => openLead(leads[0].id), 200);
}
init();
