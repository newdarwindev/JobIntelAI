# Batches: измеренные исходы до, после ошибки и продолжения

Источник: [Запуск GitHub Actions](https://github.com/newdarwindev/JobIntelAI/actions/runs/39452006080) · проверенный коммит `e348949bd47f6b11fcf7917930524d1debcc1f76`.
SHA-256 исходного содержимого: `90ea58bd7c7d24a69f78da5537a307ae6140226d281f610d6e7e11a62b0d591c`. [Машинные наблюдения](batch-comparison.json).

Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.

UI14 выбирает три authored jobs через обозначенный fixture-metadata read; snapshots/extraction/matching используют настоящие API. Unsupported fixture source и реальный stale extraction вызывают ошибки, успешные domain responses не подменяются. UI03/UI05 также проходят все 20 jobs, unit gate проверяет continuation bound на 45 items.

Completed items сохраняют точные result/attempt IDs при continuation: нет повторного POST или повторной успешной extraction/match. Before-delivery retry сохраняет key, post-commit lookup/reload не добавляет mutation. Явный replan меняет только unfinished items; другая candidate revision блокирует matching до восстановления captured selection. Empty batch ничего не отправляет.

Это counts captured batch и сервера, не качество модели. In-flight journal остаётся uncertain до доставки даже при server commit. Browser POST counts учитывают keyed snapshot/extract/match, исключая registry preparation, reads, profiles и независимую fault injection. У matching нет каталога: проверяются saved responses и operation IDs. Исходная extraction history сохранена.

| Viewport | Batch | Граница | До: зарегистрировано/извлечено | Частичные исходы | Частичный сервер | После continuation | Итоговый сервер | Browser POST | Сохранённые completed IDs |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| desktop-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| desktop-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 49b9b2b37ce74823be98da8ab16a7571 |
| desktop-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 2da517a8d57144318fc85d15e45d8c29<br>SYN-02: 10bff5be5ea842bb8ffa97a6aa9c7f93 |
| desktop-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| desktop-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: da69f3a17b95491e9e1c0da03c438d65 |
| desktop-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 6ad1525a7d1045769264d2d5fa426914<br>SYN-02: 68f1d7dcaacd4c5ca74c2d2cc41b37b4 |
| desktop-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 6cc9e7eaa6f84ee8a4a97b005af1300a |
| desktop-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 91982600d0eb40179e981a901082a4eb |
| desktop-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: f212a9845d71423d8188f47aa596190b |
| desktop-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 5e95aba8546b40b2988e888d7beebb89 |
| desktop-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 034b69d2dc3b4bf492863fe7550398d8 |
| desktop-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 526c1fef3c4a418588f29be27bd5d00d |
| desktop-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 7166568a195240cb9f1359893a8a2f97 |
| desktop-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 69d70e3c135540f6adad99fff70ad868 |
| desktop-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| desktop-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_first | 0/0 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/0 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | До прерывания завершённых items нет |
| mobile-chromium | extraction | failure_middle | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 5bb00b8b99734de0bf2ffe1725fd163f |
| mobile-chromium | extraction | failure_last | 0/0 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: a06498301153470b9b729e378f863def<br>SYN-02: 8beb9df9d94c48e18a75513f684b969e |
| mobile-chromium | matching | failure_first | 3/3 | 0 завершено / 1 ошибок / 2 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | До прерывания завершённых items нет |
| mobile-chromium | matching | failure_middle | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 57dd508c7a5b4ddfba7cae735408dc6a |
| mobile-chromium | matching | failure_last | 3/3 | 2 завершено / 1 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 9229f75560844906ad21afb89ae0fa62<br>SYN-02: 9b2c2e2ca880472aa24c447e6da9c20f |
| mobile-chromium | extraction | before_delivery | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 3a07e34fb1e044148f75b664cfc01f04 |
| mobile-chromium | extraction | after_commit_lookup_lost_reload | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: b950fdcf1ab04bb4871a0c295b952f45 |
| mobile-chromium | matching | before_delivery | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: 81cb14da887e48efbfb1c0596c8f1149 |
| mobile-chromium | matching | after_commit_lookup_lost_reload | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 575c79a78b7c40afb2eea38b217c1b3f |
| mobile-chromium | extraction | navigation_in_flight | 0/0 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/2 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 6 | SYN-01: 64cf1973ad3643679eea4bd98691e18c |
| mobile-chromium | matching | navigation_in_flight | 3/3 | 1 завершено / 0 ошибок / 1 не начато / 1 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 3 | SYN-01: 747f40e0b86c46509bd633edefcabd30 |
| mobile-chromium | extraction | stale_source | 0/0 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/1 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 7 | SYN-01: 1fe8ff63ddc3466a870d7e7de6eca314 |
| mobile-chromium | matching | stale_revision | 3/3 | 1 завершено / 1 ошибок / 1 не начато / 0 неизвестно | 3/3 | 3 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 3/3 | 4 | SYN-01: cebe42ee0d134c0792f2f70824830a29 |
| mobile-chromium | extraction | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |
| mobile-chromium | matching | empty | 0/0 | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | Нет данных | 0 завершено / 0 ошибок / 0 не начато / 0 неизвестно | 0/0 | 0 | До прерывания завершённых items нет |

[Desktop UI14](../../ui-recordings/UI14-desktop-chromium.webm) · [Mobile UI14](../../ui-recordings/UI14-mobile-chromium.webm)

Панель сохраняет identities/states и prior rejected operation IDs при navigation/reload. Session storage содержит только IDs/config/selection/states, bodies и error messages читаются в память. Unknown operation блокирует continuation. Каждый exit пытается обновить authoritative state; failure обозначен как отсутствие данных.
