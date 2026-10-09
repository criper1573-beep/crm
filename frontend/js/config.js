// Все настройки CRM в одном месте

const CONFIG = {

  api: {
    base: '/api'
  },

  statuses: {
    lead:        { label: 'Лид',               color: '#5c5c5c', bg: '#e7e2d8' },
    mql:         { label: 'MQL',               color: '#0a0a0a', bg: '#f0ede6' },
    sql:         { label: 'SQL',               color: '#b02a00', bg: '#fff4f0' },
    hot:         { label: 'Горячий лид',       color: '#b02a00', bg: '#fff4f0' },
    client:      { label: 'Клиент',            color: '#0a0a0a', bg: '#f0ede6' },
    repeat:      { label: 'Повторный клиент',  color: '#0a0a0a', bg: '#ffffff' },
    drain_mql:   { label: 'Слив MQL',          color: '#5c5c5c', bg: '#e7e2d8' },
    drain_sql:   { label: 'Слив SQL',          color: '#5c5c5c', bg: '#e7e2d8' },
    drain_hot:   { label: 'Слив горячий лид',  color: '#b02a00', bg: '#fff4f0' },
  },

  budgets: {
    lo:  { label: '< 30к'   },
    mid: { label: '30–100к' },
    hi:  { label: '> 100к'  },
  },

  objectTypes: ['Квартира', 'Коммерческая', 'Дом'],

  workTypes: ['Перегородки', 'Потолки', 'Облицовка', 'Демонтаж', 'Малярные работы', 'Изделия', 'Под ключ'],

  messageSources: ['Авито', 'Телеграм', 'WhatsApp', 'Телефон'],

  telegram_username: 'Алексей',
}
