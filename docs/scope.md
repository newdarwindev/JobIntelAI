# Область redesign/local-mvp

| Возможность | Решение | Проверка |
| --- | --- | --- |
| Вставка вакансии и сведений кандидата | Оставлена | API validation, responsive layout |
| Grounded compare | Один явный OpenAI adapter; UNKNOWN при пробеле | Synthetic adapter tests; реальный вызов не выполнялся |
| Цитаты и Unicode spans | Точное вхождение обязательно | API tests |
| Сохранение, история, JSON export, рестарт | Оставлены | Тест restart/export/idempotency |
| Дублирование/неопределённость | SQLite reservation до вызова; uncertain блокирует повтор | Тест failure/pending |
| URL acquisition, SSRF proxy | Удалены; URL только reference | Нет сетевого fetch |
| Registry/import CSV, analytics, dashboards | Отложены | За пределами MVP |
| Training, notebooks, Binder, evaluation program | Удалены из активной ветки | Старые публикации доступны в Git истории |
| CPU/emulator/PostgreSQL/Compose/deployment combinations | Удалены из активной ветки | SQLite single-process |
| Старые данные | Read-only copy/import; archive всех таблиц | Synthetic migration test |

Новые критерии: пользователь вставляет произвольные тексты, получает явную ошибку либо проверяемые цитаты; открывает запись после перезапуска; выгружает JSON; неправильная цитата не сохраняется; повтор ключа не вызывает модель снова. Синтетический provider в тестах не доказывает качество реальной модели. Семантические ошибки возможны и требуют проверки человеком.

Открытые issues/PRs не закрывались и не сливались. Предложение после review: #40/#41 отметить как уже реализованные прежними #45/#46; #93, #57, #77–92, #71–74 закрыть как superseded новым scope после обсуждения; #94 не переносить автоматически; #49–51 покрыть минимальной историей и экспортом с новыми критериями; #56 оставить открытой как model-quality; #69 переписать под эту карту. Два прежних draft PR проверить отдельно, закрывать лишь после решения владельца. Старые 63 обязательства не объявлены выполненными.

В этом PR не выполнялись hosted inference, платные вызовы, PostgreSQL migration и старые 30 browser journeys. Новые проверки: `make check`, `make build`.
