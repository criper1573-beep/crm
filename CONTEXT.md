# Монтаж CRM — Контекст проекта

## Стек
- Backend: Python, FastAPI, SQLite
- Frontend: HTML, CSS, vanilla JavaScript
- Запуск: uvicorn backend.main:app --reload (из корня проекта)
- База данных: data/crm.db (SQLite)

## Структура
- backend/main.py     — FastAPI роуты
- backend/database.py — работа с SQLite
- backend/models.py   — модель лида
- frontend/           — весь фронтенд
- data/context.txt    — контекст бизнеса для AI-функций

## Что сделано
- [x] Структура проекта
- [x] Модель данных (таблица leads)
- [x] CRUD эндпоинты /api/leads
- [x] Статика фронтенда раздаётся с /
- [x] Авто-резюме из переписки и заметок (GRS AI API)

## В процессе
- [ ] Генерация ответа клиенту с контекстным файлом
- [ ] Автоклассификация статуса по последним сообщениям

## Соглашения
- Статусы лида: lead, mql, sql, hot, client, repeat, drain_mql, drain_sql, drain_hot
- Бюджеты: lo (<30к), mid (30-100к), hi (>100к)
- Типы объектов: Квартира, Коммерческая, Дом
