# FLOW CRM

## Правила качества

Короткие правила для агентов в этом репозитории:

- `.cursor/rules/security.mdc` — секреты, доступ к чужому лиду по ID, загрузка файлов
- `.cursor/rules/errors-no-silent-failures.mdc` — не глотать ошибки и не подменять сумму нулём
- `.cursor/rules/money-tdd.mdc` — TDD только для сумм сделок, бюджетов и платежей
- `.cursor/rules/safety.mdc` — без явной задачи не трогать прод, `.env` и разрушительные команды
- `.cursor/rules/verification.mdc` — перед «готово» запустить проверку и подтвердить пункты

Проверка: `npm run verify` (то же, что `bash scripts/verify.sh`).
