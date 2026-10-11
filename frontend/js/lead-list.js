/* Сортировка списка лидов и период по дате добавления (created_at). */
(function (root, factory) {
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.LeadList = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  var SORTS = ['created_desc', 'created_asc', 'last_message'];
  var PERIODS = ['week', 'month', 'prev_month', 'quarter', 'year', 'all', 'custom'];
  var PERIOD_ALIASES = { '7': 'week', '30': 'month', '90': 'quarter' };

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

  function parseYmd(raw) {
    var s = String(raw || '').trim();
    var iso = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (iso) return iso[1] + '-' + pad(iso[2]) + '-' + pad(iso[3]);
    var dmy = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\D|$)/);
    if (dmy) return dmy[3] + '-' + pad(dmy[2]) + '-' + pad(dmy[1]);
    var shortY = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2})(?:\D|$)/);
    if (shortY) return String(2000 + Number(shortY[3])) + '-' + pad(shortY[2]) + '-' + pad(shortY[1]);
    return '';
  }

  function leadCreatedYmd(lead) {
    return parseYmd(lead && lead.created_at);
  }

  function canonicalPeriod(period) {
    if (PERIOD_ALIASES[period]) return PERIOD_ALIASES[period];
    if (PERIODS.indexOf(period) >= 0) return period;
    return 'month';
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

  function previousCalendarMonth(today) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(today || '');
    if (!m) return { start: '', end: '' };
    var year = Number(m[1]);
    var month = Number(m[2]);
    var prevMonth = month - 1;
    var prevYear = year;
    if (prevMonth < 1) {
      prevMonth = 12;
      prevYear -= 1;
    }
    var endDate = new Date(prevYear, prevMonth, 0);
    return {
      start: prevYear + '-' + pad(prevMonth) + '-01',
      end: formatYmd(endDate),
    };
  }

  function periodRange(period, from, to, today) {
    var key = canonicalPeriod(period);
    if (key === 'all') return { start: '', end: '' };
    if (key === 'week') return { start: addDays(today, -6), end: today };
    if (key === 'month') return { start: addDays(today, -29), end: today };
    if (key === 'quarter') return { start: addDays(today, -89), end: today };
    if (key === 'year') return { start: addDays(today, -364), end: today };
    if (key === 'prev_month') return previousCalendarMonth(today);
    var start = from || '';
    var end = to || '';
    if (start && end && start > end) {
      var swap = start;
      start = end;
      end = swap;
    }
    return { start: start, end: end };
  }

  function createdPeriodRange(period, from, to, today) {
    return periodRange(period, from, to, today);
  }

  function ymdInRange(ymd, start, end) {
    if (!ymd) return false;
    if (start && ymd < start) return false;
    if (end && ymd > end) return false;
    return true;
  }

  function leadMatchesCreatedPeriod(lead, period, from, to, today) {
    if (canonicalPeriod(period) === 'all') return true;
    var ymd = leadCreatedYmd(lead);
    if (!ymd) return false;
    var range = periodRange(period, from, to, today);
    return ymdInRange(ymd, range.start, range.end);
  }

  function periodCaption(period, from, to, today) {
    var key = canonicalPeriod(period);
    var range = periodRange(key, from, to, today);
    if (key === 'all') return 'Показаны лиды, добавленные за всё время';
    if (key === 'custom') {
      if (range.start && range.end) return 'Показаны лиды, добавленные с ' + ymdToDmy(range.start) + ' по ' + ymdToDmy(range.end);
      if (range.start) return 'Показаны лиды, добавленные с ' + ymdToDmy(range.start);
      if (range.end) return 'Показаны лиды, добавленные по ' + ymdToDmy(range.end);
      return 'Укажите даты добавления лида';
    }
    if (key === 'prev_month' && range.start && range.end) {
      return 'Показаны лиды, добавленные за прошлый месяц (' + ymdToDmy(range.start) + '–' + ymdToDmy(range.end) + ')';
    }
    var days = { week: '7', month: '30', quarter: '90', year: '365' };
    return 'Показаны лиды, добавленные за последние ' + (days[key] || '30') + ' дней';
  }

  function dealAmount(lead) {
    if (lead && lead.has_multiple_objects && lead.objects && lead.objects.length) {
      return lead.objects.reduce(function (sum, obj) { return sum + (Number(obj.deal_amount) || 0); }, 0);
    }
    return Number(lead && lead.deal_amount) || 0;
  }

  function leadInWonPeriod(lead, period, from, to, today) {
    var status = lead && lead.status;
    if (status !== 'client' && status !== 'repeat') return false;
    var range = periodRange(period, from, to, today);
    var payments = (lead && lead.payments) || [];
    var paidIn = false;
    for (var i = 0; i < payments.length; i++) {
      if (ymdInRange(parseYmd(payments[i] && payments[i].paid_at), range.start, range.end)) paidIn = true;
    }
    if (paidIn) return true;
    if (payments.length) return false;
    return ymdInRange(leadCreatedYmd(lead), range.start, range.end);
  }

  function sumPayments(leads, period, from, to, today) {
    var range = periodRange(period, from, to, today);
    var sum = 0;
    (leads || []).forEach(function (lead) {
      ((lead && lead.payments) || []).forEach(function (payment) {
        if (ymdInRange(parseYmd(payment && payment.paid_at), range.start, range.end)) sum += Number(payment.amount) || 0;
      });
    });
    return sum;
  }

  function sumDealAmounts(leads, period, from, to, today) {
    return (leads || []).reduce(function (sum, lead) {
      return sum + (leadInWonPeriod(lead, period, from, to, today) ? dealAmount(lead) : 0);
    }, 0);
  }

  function countWon(leads, period, from, to, today) {
    var clients = 0;
    var repeats = 0;
    (leads || []).forEach(function (lead) {
      if (!leadInWonPeriod(lead, period, from, to, today)) return;
      if (lead.status === 'client') clients += 1;
      else if (lead.status === 'repeat') repeats += 1;
    });
    return { clients: clients, repeats: repeats };
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
    canonicalPeriod: canonicalPeriod,
    periodRange: periodRange,
    parseYmd: parseYmd,
    sumPayments: sumPayments,
    sumDealAmounts: sumDealAmounts,
    countWon: countWon,
    leadInWonPeriod: leadInWonPeriod,
    sortLeads: sortLeads,
    parseLeadHash: parseLeadHash,
    leadHash: leadHash,
    leadUrl: leadUrl,
    isListHash: isListHash,
    missingLeadMessage: missingLeadMessage,
    leadRouteAction: leadRouteAction,
  };
});
