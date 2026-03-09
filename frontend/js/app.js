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
  if(['drain_g','drain_m','drain_s'].includes(s)) return 'drain';
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
  const noReply = leads.filter(l => getStatusGroup(l.status)==='hot' && l.msgs.length > 0 && !l.msgs[l.msgs.length-1].out);
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
    const matchFilter = currentFilter === 'all' || getStatusGroup(l.status) === currentFilter;
    const matchSearch = !q || l.name.toLowerCase().includes(q) || l.address.toLowerCase().includes(q) || l.comment.toLowerCase().includes(q);
    return matchFilter && matchSearch;
  });

  const el = document.getElementById('leadsList');
  el.innerHTML = filtered.map(l => {
    const si = getStatusInfo(l.status);
    const bi = BUDGET[l.budget];
    const hasNewMsg = l.msgs.length > 0 && !l.msgs[l.msgs.length-1].out;
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
      ${l.comment ? `<div class="lc-comment">${l.comment}</div>` : ''}
    </div>`;
  }).join('');
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
        <button class="dbtn" onclick="cycleStatus(${l.id})">Статус →</button>
        <button class="dbtn primary" onclick="switchTab('msgs')">💬 Ответить</button>
        <button type="button" class="dbtn" onclick="deleteLead(${l.id})" style="color:var(--hot);border-color:rgba(255,77,109,0.5)">Удалить лид</button>
      </div>
    </div>
    <div class="dtabs">
      <div class="dtab ${activeTab==='overview'?'active':''}" onclick="switchTab('overview')">🗂 Обзор</div>
      <div class="dtab ${activeTab==='msgs'?'active':''}" onclick="switchTab('msgs')">💬 Переписка (${l.msgs.length})</div>
      <div class="dtab ${activeTab==='calls'?'active':''}" onclick="switchTab('calls')">📞 Звонки (${l.calls.length})</div>
    </div>
    <div class="tab-body fade-in" id="tabBody">${renderTab(l)}</div>
  `;
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
}

function renderTab(l) {
  if(activeTab==='overview') return renderOverview(l);
  if(activeTab==='msgs') return renderMsgs(l);
  if(activeTab==='calls') return renderCalls(l);
  return '';
}

// OVERVIEW
function renderOverview(l) {
  const si = getStatusInfo(l.status);
  const bi = BUDGET[l.budget];
  const lastMsg = l.msgs.length ? l.msgs[l.msgs.length-1] : null;
  const tone = getStatusGroup(l.status)==='hot' ? 'Горячий, готов к сотрудничеству' :
               getStatusGroup(l.status)==='client' ? 'Клиент, договорённость достигнута' :
               getStatusGroup(l.status)==='drain' ? 'Слив — не конвертировался' :
               getStatusGroup(l.status)==='repeat' ? 'Повторный клиент — лояльный' : 'SQL — ждёт финального решения';

  return `
    <div class="ai-card">
      <div class="ai-label"><span class="ai-spin">✦</span> AI-РЕЗЮМЕ ЛИДА · авто из переписки</div>
      <div class="ai-grid">
        <div class="ai-field"><div class="aif-label">Статус</div><div class="aif-val ${getStatusGroup(l.status)==='hot'?'hot':getStatusGroup(l.status)==='client'?'ok':''}">${si.label}</div></div>
        <div class="ai-field"><div class="aif-label">Тип объекта</div><div class="aif-val">${l.obj||'Не указан'}</div></div>
        <div class="ai-field"><div class="aif-label">Бюджет</div><div class="aif-val accent">${bi?bi.label:'Не указан'}</div></div>
        <div class="ai-field"><div class="aif-label">Адрес</div><div class="aif-val">${l.address||'Не указан'}</div></div>
        <div class="ai-field"><div class="aif-label">Последний контакт</div><div class="aif-val">${l.date||'—'}</div></div>
        <div class="ai-field"><div class="aif-label">Тон клиента</div><div class="aif-val">${tone}</div></div>
      </div>
      ${l.comment ? `<div class="ai-comment">💬 <b>Ваш комментарий:</b> ${l.comment}</div>` : ''}
      ${lastMsg ? `<div class="ai-comment" style="margin-top:8px">📩 <b>Последнее сообщение:</b> ${lastMsg.text}</div>` : ''}
      <button class="dbtn" style="margin-top:10px;font-size:9px" onclick="">↺ Обновить из переписки</button>
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
function renderMsgs(l) {
  return `
    <div class="msg-thread">
      ${l.msgs.length===0
        ? `<div style="text-align:center;color:var(--muted);font-size:10px;padding:30px">Переписки пока нет</div>`
        : l.msgs.map((m,i)=>`
          <div class="tmsg ${m.out?'out':'in'}" style="animation-delay:${i*.04}s">
            <div class="tmsg-av ${m.out?'me':'cli'}">${m.out?'Я':l.name[0]}</div>
            <div class="tmsg-body">
              <div class="tmsg-bubble">${m.text}</div>
              <div class="tmsg-time">${m.time}</div>
              ${m.src?`<div class="src-badge">📱 ${m.src}</div>`:''}
            </div>
          </div>`).join('')
      }
    </div>
    <div class="msg-input-area" style="margin-top:14px">
      <textarea placeholder="Ответить клиенту..." onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg(${l.id})}"></textarea>
      <button class="dbtn primary" onclick="sendMsg(${l.id})">→</button>
    </div>
    <div style="font-size:8px;color:var(--muted);margin-top:5px;text-align:center">Enter для отправки · Shift+Enter — перенос строки</div>
  `;
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

// SEND MSG
function sendMsg(id) {
  const l = leads.find(x=>x.id===id);
  const ta = document.querySelector('.msg-input-area textarea');
  const txt = ta?.value.trim();
  if(!txt) return;
  l.msgs.push({out:true,text:txt,time:'только что',src:null});
  ta.value='';
  switchTab('msgs');
}

// STATUS CYCLE
const statusOrder = ['hot','client','repeat','sql','drain_g'];
function cycleStatus(id) {
  const l = leads.find(x=>x.id===id);
  const idx = statusOrder.indexOf(l.status);
  l.status = statusOrder[(idx+1)%statusOrder.length];
  renderDetail();
  renderList();
  updateStats();
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
  const raw = await apiGetLeads();
  leads = (raw || []).map(mapLeadFromApi);
  updateStats();
  renderList();
  if (leads.length) setTimeout(() => openLead(leads[0].id), 200);
}
init();
