Режим эксперимента: fake; запрошенная модель: fake-fixture.
Создан: 2026-10-09T12:03:13.161712+00:00; SHA-256 корпуса: `35432171e14665c2cd242caffd878d7b51eccf4b8244d2357bc011e4d533a1ca`.
SHA-256 конфигурации: `5bde651d55f552da37f42e972312def88d41559e8135fbf1e42636b186c330b8`. [Полный отчёт](report.json); [Повторно подсчитанные метрики](scores.json).

| Конфигурация | Успех / случаи | Ошибки | Precision | Recall | Тип | Цитата | Неподтверждённые claims | Верный unknown | Секунды на вакансию | Tokens вход/выход | Стоимость USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| A | 20/25 | 5 | 0.7727 | 0.7727 | 0.9412 | 1.0000 | 0.1071 | 1.0000 | 0.0045 | нет данных | нет данных |
| B | 20/25 | 5 | 0.7727 | 0.7727 | 0.9412 | 1.0000 | 0.1071 | 1.0000 | 0.0045 | нет данных | нет данных |
| C | 20/25 | 5 | 0.9545 | 0.9545 | 0.9524 | 1.0000 | 0.1071 | 1.0000 | 0.0064 | нет данных | нет данных |

Метрики относятся к успешным случаям; ошибки и исходные ответы сохранены в полном отчёте. Matching использует gold-требования и подтверждённые сведения кандидата. Нулевые знаменатели и неизмеренные usage/cost/LLM latency остаются неизвестными.
Регрессия fake provider: качество live-модели и оплаченный usage не измеряются. Исходные fixture-ответы одинаковы в A/B/C, только C применяет normalization.
- A / REV-21: provider_unavailable
- A / REV-22: provider_unavailable
- A / REV-23: provider_unavailable
- A / REV-24: provider_unavailable
- A / REV-25: provider_unavailable
- A / REV-02: 1/1 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
- A / REV-13: 1/2 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
- A / REV-14: 1/2 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
- B / REV-21: provider_unavailable
- B / REV-22: provider_unavailable
- B / REV-23: provider_unavailable
- B / REV-24: provider_unavailable
- B / REV-25: provider_unavailable
- B / REV-02: 1/1 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
- B / REV-13: 1/2 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
- B / REV-14: 1/2 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
- C / REV-21: provider_unavailable
- C / REV-22: provider_unavailable
- C / REV-23: provider_unavailable
- C / REV-24: provider_unavailable
- C / REV-25: provider_unavailable
- C / REV-02: 1/1 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
- C / REV-13: 1/2 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
- C / REV-14: 1/2 claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника.
