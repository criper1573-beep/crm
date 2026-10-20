const assert = require('assert');
const LeadList = require('../frontend/js/lead-list.js');

const today = '2026-10-11';

function lead(id, created, message) {
  return { id: id, created_at: created, last_message_date: message || '' };
}

const range30 = LeadList.createdPeriodRange('30', '', '', today);
assert.strictEqual(range30.start, '2026-09-12');
assert.strictEqual(range30.end, '2026-10-11');

const range7 = LeadList.createdPeriodRange('7', '', '', today);
assert.strictEqual(range7.start, '2026-10-05');
assert.strictEqual(range7.end, '2026-10-11');

assert.strictEqual(LeadList.addDays('2026-03-01', -1), '2026-02-28');
assert.strictEqual(LeadList.addDays('2024-03-01', -1), '2024-02-29');

assert.strictEqual(LeadList.leadMatchesCreatedPeriod(lead(1, '2026-09-12 00:00:00'), '30', '', '', today), true);
assert.strictEqual(LeadList.leadMatchesCreatedPeriod(lead(1, '2026-09-11 23:59:59'), '30', '', '', today), false);
assert.strictEqual(LeadList.leadMatchesCreatedPeriod(lead(1, '2026-10-11 23:00:00'), '30', '', '', today), true);
assert.strictEqual(LeadList.leadMatchesCreatedPeriod(lead(1, '2026-10-12 00:00:00'), '30', '', '', today), false);
assert.strictEqual(LeadList.leadMatchesCreatedPeriod(lead(1, ''), '30', '', '', today), false);
assert.strictEqual(LeadList.leadMatchesCreatedPeriod(lead(1, ''), 'all', '', '', today), true);
assert.strictEqual(LeadList.leadMatchesCreatedPeriod(lead(1, '01.10.2026'), 'custom', '2026-10-11', '2026-09-01', today), true);

const swapped = LeadList.createdPeriodRange('custom', '2026-10-11', '2026-09-01', today);
assert.strictEqual(swapped.start, '2026-09-01');
assert.strictEqual(swapped.end, '2026-10-11');
assert.ok(LeadList.periodCaption('30', '', '', today).includes('30'));
assert.ok(LeadList.periodCaption('all', '', '', today).includes('всё время'));

const rows = [
  lead(1, '2026-01-01 00:00:00', '2026-01-02 00:00:00'),
  lead(2, '2026-06-01 00:00:00', ''),
  lead(3, '2026-06-01 00:00:00', '2026-08-01 00:00:00'),
  lead(4, '2026-06-01 00:00:00', '2026-08-01 00:00:00'),
  lead(5, '', '2026-09-01 00:00:00'),
];

assert.deepStrictEqual(LeadList.sortLeads(rows, 'created_desc').map(r => r.id), [4, 3, 2, 1, 5]);
assert.deepStrictEqual(LeadList.sortLeads(rows, 'created_asc').map(r => r.id), [1, 2, 3, 4, 5]);
assert.deepStrictEqual(LeadList.sortLeads(rows, 'last_message').map(r => r.id), [5, 4, 3, 1, 2]);
assert.deepStrictEqual(LeadList.sortLeads(rows, 'unknown').map(r => r.id), LeadList.sortLeads(rows, 'created_desc').map(r => r.id));

assert.strictEqual(LeadList.parseLeadHash('#lead/15'), 15);
assert.strictEqual(LeadList.parseLeadHash('lead/15'), 15);
assert.strictEqual(LeadList.parseLeadHash('#lead/012'), null);
assert.strictEqual(LeadList.parseLeadHash('#lead/0'), null);
assert.strictEqual(LeadList.parseLeadHash('#lead/-3'), null);
assert.strictEqual(LeadList.parseLeadHash('#lead/1.5'), null);
assert.strictEqual(LeadList.parseLeadHash('#lead/'), null);
assert.strictEqual(LeadList.parseLeadHash('#lead/15/notes'), null);
assert.strictEqual(LeadList.parseLeadHash('#lead/abc'), null);
assert.strictEqual(LeadList.parseLeadHash(''), null);
assert.strictEqual(LeadList.parseLeadHash('#'), null);
assert.strictEqual(LeadList.parseLeadHash('#lead/9007199254740993'), null);
assert.strictEqual(LeadList.leadHash(15), '#lead/15');
assert.strictEqual(LeadList.leadHash('15'), '#lead/15');
assert.strictEqual(LeadList.leadHash(0), '');
assert.strictEqual(LeadList.leadHash('012'), '');
assert.strictEqual(LeadList.leadUrl('https://crm.flowcabinet.ru', '/', '', 15), 'https://crm.flowcabinet.ru/#lead/15');
assert.strictEqual(LeadList.leadUrl('https://crm.flowcabinet.ru', '/', '?x=1', 15), 'https://crm.flowcabinet.ru/?x=1#lead/15');
assert.strictEqual(LeadList.leadUrl('https://crm.flowcabinet.ru', '/', '', 0), '');
assert.strictEqual(LeadList.isListHash(''), true);
assert.strictEqual(LeadList.isListHash('#'), true);
assert.strictEqual(LeadList.isListHash('#lead/15'), false);
assert.strictEqual(LeadList.missingLeadMessage(15), 'Лид #15 не найден');
assert.deepStrictEqual(LeadList.leadRouteAction('#lead/15', [15, 16], null), { type: 'open', id: 15 });
assert.deepStrictEqual(LeadList.leadRouteAction('#lead/15', [15, 16], 15), { type: 'keep', id: 15 });
assert.deepStrictEqual(LeadList.leadRouteAction('#lead/99', [15], 15), { type: 'missing', id: 99 });
assert.deepStrictEqual(LeadList.leadRouteAction('', [15], 15), { type: 'list', id: null });
assert.deepStrictEqual(LeadList.leadRouteAction('#', [15], 15), { type: 'list', id: null });
assert.deepStrictEqual(LeadList.leadRouteAction('#other', [15], 15), { type: 'ignore', id: null });

assert.strictEqual(LeadList.parseSearchId('423'), 423);
assert.strictEqual(LeadList.parseSearchId('#423'), 423);
assert.strictEqual(LeadList.parseSearchId('  #423 '), 423);
assert.strictEqual(LeadList.parseSearchId('#0423'), null);
assert.strictEqual(LeadList.parseSearchId('0423'), null);
assert.strictEqual(LeadList.parseSearchId('423a'), null);
assert.strictEqual(LeadList.parseSearchId('#lead/423'), null);
assert.strictEqual(LeadList.parseSearchId(''), null);

const searchRows = [
  { id: 5, name: '423', address: '', comment: '', created_at: '2026-10-01 00:00:00' },
  { id: 423, name: 'Борис', address: '', comment: '', phone: '', created_at: '2020-01-01 00:00:00' },
  { id: 9, name: 'Другой', address: 'дом 423', comment: '', created_at: '2026-08-01 00:00:00' },
  { id: 8, name: 'Глеб #423', address: '', comment: 'заявка', created_at: '2026-09-01 00:00:00' },
  { id: 11, name: 'Пётр', address: '', comment: '', phone: '423000', created_at: '2026-10-02 00:00:00' },
  { id: 4230, name: 'Длинный', address: '', comment: '', created_at: '2026-07-01 00:00:00' },
];

assert.strictEqual(LeadList.leadMatchesSearch(searchRows[1], '423'), true);
assert.strictEqual(LeadList.leadMatchesSearch(searchRows[1], '#423'), true);
assert.strictEqual(LeadList.leadMatchesSearch(searchRows[1], '  #423 '), true);
assert.strictEqual(LeadList.leadMatchesSearch(searchRows[0], '423'), true);
assert.strictEqual(LeadList.leadMatchesSearch(searchRows[2], '423'), true);
assert.strictEqual(LeadList.leadMatchesSearch(searchRows[3], '#423'), true);
assert.strictEqual(LeadList.leadMatchesSearch(searchRows[2], '#423'), false);
assert.strictEqual(LeadList.leadMatchesSearch(searchRows[4], '423'), false);
assert.strictEqual(LeadList.leadMatchesSearch(searchRows[5], '423'), false);
assert.strictEqual(LeadList.leadMatchesSearch({ id: 1, name: 'Анна' }, 'ан'), true);
assert.strictEqual(LeadList.leadMatchesSearch({ id: 1, name: 'Анна', address: 'Ленина', comment: 'Срочно' }, 'ленина'), true);
assert.strictEqual(LeadList.leadMatchesSearch({ id: 1, name: 'Анна', address: 'Ленина', comment: 'Срочно' }, 'СРОЧНО'), true);
assert.strictEqual(LeadList.leadMatchesSearch({ id: 1, name: 'Анна' }, ''), true);

const byNumber = searchRows.filter(function (row) { return LeadList.leadMatchesSearch(row, '423'); });
const byNumberSorted = LeadList.orderSearchHits(LeadList.sortLeads(byNumber, 'created_desc'), '423');
assert.deepStrictEqual(byNumberSorted.map(function (row) { return row.id; }), [423, 5, 8, 9]);
assert.deepStrictEqual(
  LeadList.orderSearchHits(LeadList.sortLeads(byNumber, 'created_desc'), '#423').map(function (row) { return row.id; }),
  [423, 5, 8, 9]
);
const byName = searchRows.filter(function (row) { return LeadList.leadMatchesSearch(row, 'другой'); });
assert.deepStrictEqual(
  LeadList.orderSearchHits(LeadList.sortLeads(byName, 'created_desc'), 'другой').map(function (row) { return row.id; }),
  [9]
);
assert.deepStrictEqual(
  LeadList.orderSearchHits(LeadList.sortLeads(searchRows, 'created_asc'), '42').filter(function (row) {
    return LeadList.leadMatchesSearch(row, '42');
  }).map(function (row) { return row.id; }),
  [9, 8, 5]
);

assert.strictEqual(LeadList.parseYmd('2.12.25'), '2025-12-02');
assert.strictEqual(LeadList.parseYmd('02.12.2025'), '2025-12-02');
assert.strictEqual(LeadList.parseYmd('2.12.25 12:00'), '2025-12-02');
assert.strictEqual(LeadList.leadCreatedYmd({ created_at: '2.12.25' }), '2025-12-02');
assert.strictEqual(LeadList.canonicalPeriod('30'), 'month');
assert.strictEqual(LeadList.canonicalPeriod('7'), 'week');
assert.strictEqual(LeadList.canonicalPeriod('90'), 'quarter');

const prev = LeadList.periodRange('prev_month', '', '', today);
assert.strictEqual(prev.start, '2026-09-01');
assert.strictEqual(prev.end, '2026-09-30');
assert.deepStrictEqual(LeadList.periodRange('prev_month', '', '', '2026-01-15'), { start: '2025-12-01', end: '2025-12-31' });
assert.deepStrictEqual(LeadList.periodRange('prev_month', '', '', '2024-03-10'), { start: '2024-02-01', end: '2024-02-29' });
assert.deepStrictEqual(LeadList.periodRange('prev_month', '', '', '2025-03-10'), { start: '2025-02-01', end: '2025-02-28' });
assert.strictEqual(LeadList.periodRange('quarter', '', '', today).start, '2026-07-14');
assert.strictEqual(LeadList.periodRange('year', '', '', today).start, '2025-10-12');

const imported = {
  id: 1, status: 'client', created_at: '2026-10-11 09:00:00', deal_amount: 500000,
  payments: [{ paid_at: '2026-04-15', amount: 100000 }, { paid_at: '2.12.25', amount: 5000 }],
};
const fresh = { id: 2, status: 'client', created_at: '2026-10-10 09:00:00', deal_amount: 50000, payments: [] };
const repeat = {
  id: 3, status: 'repeat', created_at: '2024-01-01 00:00:00', deal_amount: 80000,
  payments: [{ paid_at: '2026-10-08', amount: 70000 }],
};
const sample = [imported, fresh, repeat];
assert.strictEqual(LeadList.sumPayments(sample, 'week', '', '', today), 70000);
assert.strictEqual(LeadList.leadInWonPeriod(imported, 'week', '', '', today), false);
assert.strictEqual(LeadList.leadInWonPeriod(fresh, 'week', '', '', today), true);
assert.strictEqual(LeadList.leadInWonPeriod(repeat, 'week', '', '', today), true);
assert.deepStrictEqual(LeadList.countWon(sample, 'week', '', '', today), { clients: 1, repeats: 1 });
assert.strictEqual(LeadList.sumDealAmounts(sample, 'week', '', '', today), 130000);
assert.strictEqual(LeadList.sumPayments(sample, 'custom', '2025-12-01', '2025-12-31', today), 5000);

console.log('lead-list ok');
