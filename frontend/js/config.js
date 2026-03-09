// Все настройки CRM в одном месте

const CONFIG = {

  api: {
    base: 'http://127.0.0.1:8000/api'
  },

  statuses: {
    lead:        { label: 'Лид',               color: '#7a7a9a', bg: 'rgba(122,122,154,0.12)' },
    mql:         { label: 'MQL',               color: '#7c5cfc', bg: 'rgba(124,92,252,0.12)'  },
    sql:         { label: 'SQL',               color: '#f5a623', bg: 'rgba(245,166,35,0.12)'  },
    hot:         { label: 'Горячий лид',       color: '#ff4d6d', bg: 'rgba(255,77,109,0.12)'  },
    client:      { label: 'Клиент',            color: '#00d68f', bg: 'rgba(0,214,143,0.12)'   },
    repeat:      { label: 'Повторный клиент',  color: '#00e5ff', bg: 'rgba(0,229,255,0.10)'   },
    drain_mql:   { label: 'Слив MQL',          color: '#c0392b', bg: 'rgba(192,57,43,0.12)'   },
    drain_sql:   { label: 'Слив SQL',          color: '#e74c3c', bg: 'rgba(231,76,60,0.12)'   },
    drain_hot:   { label: 'Слив горячий лид',  color: '#ff6b35', bg: 'rgba(255,107,53,0.12)'  },
  },

  budgets: {
    lo:  { label: '< 30к'   },
    mid: { label: '30–100к' },
    hi:  { label: '> 100к'  },
  },

  objectTypes: ['Квартира', 'Коммерческая', 'Дом'],

  messageSources: ['Авито', 'Телеграм', 'WhatsApp', 'Телефон'],

  telegram_username: 'Алексей',
}
