/* Сортировка списка лидов и период по дате добавления (created_at). */
(function (root, factory) {
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.LeadList = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  var SORTS = ['created_desc', 'created_asc', 'last_message'];
  var PERIODS = ['7', '30', '90', 'all', 'custom'];

  function pad(n) { return String(n).padStart(2, '0'); }

  function formatYmd(date) {
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
  }

  function addDays(ymd, delta) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd || '');
    if (!m) return '';
    var dt = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    dt.setDate(dt.getDate() + delta);
    return formatYmd(dt);
  }

  function ymdToDmy(ymd) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd || '');
    return m ? (m[3] + '.' + m[2] + '.' + m[1]) : '';
  }

  function leadCreatedYmd(lead) {
    var raw = String((lead && lead.created_at) || '').trim();
    var iso = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (iso) return iso[1] + '-' + pad(iso[2]) + '-' + pad(iso[3]);
    var dmy = raw.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})/);
    if (dmy) return dmy[3] + '-' + pad(dmy[2]) + '-' + pad(dmy[1]);
    return '';
  }

  function stamp(value) {
    var raw = String(value || '').trim();
    var iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
    if (!iso) {
      var ymd = leadCreatedYmd({ created_at: raw });
      return ymd ? ymd + ' 00:00:00' : '';
    }
    return iso[1] + '-' + iso[2] + '-' + iso[3] + ' ' + (iso[4] || '00') + ':' + (iso[5] || '00') + ':' + (iso[6] || '00');
  }

  function leadId(lead) {
    var id = Number(lead && lead.id);
    return isFinite(id) ? id : 0;
  }

  function createdPeriodRange(period, from, to, today) {
    var key = PERIODS.indexOf(period) >= 0 ? period : '30';
    if (key === 'all') return { start: '', end: '' };
    if (key === '7' || key === '30' || key === '90') {
      var n = Number(key);
      return { start: addDays(today, -(n - 1)), end: today };
    }
    var start = from || '';
    var end = to || '';
    if (start && end && start > end) {
      var swap = start;
      start = end;
      end = swap;
    }
    return { start: start, end: end };
  }

  function leadMatchesCreatedPeriod(lead, period, from, to, today) {
    var key = PERIODS.indexOf(period) >= 0 ? period : '30';
    if (key === 'all') return true;
    var ymd = leadCreatedYmd(lead);
    if (!ymd) return false;
    var range = createdPeriodRange(key, from, to, today);
    if (range.start && ymd < range.start) return false;
    if (range.end && ymd > range.end) return false;
    return true;
  }

  function periodCaption(period, from, to, today) {
    var key = PERIODS.indexOf(period) >= 0 ? period : '30';
    if (key === 'all') return 'Показаны лиды, добавленные за всё время';
    if (key === 'custom') {
      var range = createdPeriodRange('custom', from, to, today);
      if (range.start && range.end) return 'Показаны лиды, добавленные с ' + ymdToDmy(range.start) + ' по ' + ymdToDmy(range.end);
      if (range.start) return 'Показаны лиды, добавленные с ' + ymdToDmy(range.start);
      if (range.end) return 'Показаны лиды, добавленные по ' + ymdToDmy(range.end);
      return 'Укажите даты добавления лида';
    }
    return 'Показаны лиды, добавленные за последние ' + key + ' дней';
  }

  function compareCreatedDesc(a, b) {
    var sa = stamp(a && a.created_at);
    var sb = stamp(b && b.created_at);
    if (sa !== sb) {
      if (!sa) return 1;
      if (!sb) return -1;
      return sa < sb ? 1 : -1;
    }
    return leadId(b) - leadId(a);
  }

  function compareCreatedAsc(a, b) {
    var sa = stamp(a && a.created_at);
    var sb = stamp(b && b.created_at);
    if (sa !== sb) {
      if (!sa) return 1;
      if (!sb) return -1;
      return sa < sb ? -1 : 1;
    }
    return leadId(a) - leadId(b);
  }

  function compareLastMessage(a, b) {
    var sa = stamp(a && a.last_message_date);
    var sb = stamp(b && b.last_message_date);
    if (sa !== sb) {
      if (!sa) return 1;
      if (!sb) return -1;
      return sa < sb ? 1 : -1;
    }
    return leadId(b) - leadId(a);
  }

  function sortLeads(leads, mode) {
    var list = (leads || []).slice();
    var cmp = compareCreatedDesc;
    if (mode === 'created_asc') cmp = compareCreatedAsc;
    else if (mode === 'last_message') cmp = compareLastMessage;
    list.sort(cmp);
    return list;
  }

  var MAX_LEAD_ID = 9007199254740991;

  function parseLeadHash(hash) {
    var raw = String(hash == null ? '' : hash);
    if (raw.charAt(0) === '#') raw = raw.slice(1);
    var m = /^lead\/([1-9]\d*)$/.exec(raw);
    if (!m) return null;
    var id = Number(m[1]);
    if (!isFinite(id) || id <= 0 || id > MAX_LEAD_ID || String(id) !== m[1]) return null;
    return id;
  }

  function leadHash(id) {
    if (typeof id === 'number') {
      if (!isFinite(id) || id <= 0 || Math.floor(id) !== id || id > MAX_LEAD_ID) return '';
      return '#lead/' + id;
    }
    var s = String(id == null ? '' : id);
    if (!/^[1-9]\d*$/.test(s)) return '';
    var n = Number(s);
    if (!isFinite(n) || n > MAX_LEAD_ID || String(n) !== s) return '';
    return '#lead/' + s;
  }

  function leadUrl(origin, pathname, search, id) {
    var hash = leadHash(id);
    if (!hash) return '';
    return String(origin || '') + String(pathname == null ? '' : pathname) + String(search == null ? '' : search) + hash;
  }

  function isListHash(hash) {
    var raw = String(hash == null ? '' : hash);
    return raw === '' || raw === '#';
  }

  function missingLeadMessage(id) {
    return 'Лид #' + id + ' не найден';
  }

  function leadRouteAction(hash, knownIds, activeId) {
    var id = parseLeadHash(hash);
    if (id != null) {
      var known = false;
      var list = knownIds || [];
      for (var i = 0; i < list.length; i++) {
        if (list[i] === id) { known = true; break; }
      }
      if (!known) return { type: 'missing', id: id };
      if (activeId === id) return { type: 'keep', id: id };
      return { type: 'open', id: id };
    }
    if (isListHash(hash)) return { type: 'list', id: null };
    return { type: 'ignore', id: null };
  }

  return {
    SORTS: SORTS,
    PERIODS: PERIODS,
    addDays: addDays,
    leadCreatedYmd: leadCreatedYmd,
    createdPeriodRange: createdPeriodRange,
    leadMatchesCreatedPeriod: leadMatchesCreatedPeriod,
    periodCaption: periodCaption,
    sortLeads: sortLeads,
    parseLeadHash: parseLeadHash,
    leadHash: leadHash,
    leadUrl: leadUrl,
    isListHash: isListHash,
    missingLeadMessage: missingLeadMessage,
    leadRouteAction: leadRouteAction,
  };
});
