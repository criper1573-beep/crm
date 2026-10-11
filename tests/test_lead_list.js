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

console.log('lead-list ok');
