# Доказательства notebook execution

Кратко: реальный offline fixture run, точный пересчёт сохранённых scores и отказ
preflight без создания output. Эти результаты не измеряют качество LLM.

Исходный коммит: `c51a97dea5b49db213ce2054140036fbdeaaa87a`; dirty: `True`.
SHA-256 исходного Python-кода: `c6167d89f5ae8f74edc17ce823f6739185ed24efda446249ff329f65a8d75382`.

| Сценарий | Видимый результат | Доказательства |
| --- | --- | --- |
| Fixture | succeeded; fake evidence; tokens/cost не измерялись | [manifest](fixture/manifest.json), [report](fixture/report.json), [сравнение](fixture/comparison.md) |
| Сохранённый report | succeeded; без новой inference; scores совпадают побайтово | [manifest](saved/manifest.json), [scores](saved/scores.json) |
| Неверный corpus pin | exit 2, corpus_checksum; output не создан | [Структурированные исходы](evidence.json) |

| Результат тестов | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| pr93-unit.xml | 55 | 0 | 0 | 0 |
| junit.xml | 930 | 0 | 0 | 0 |

Полные [машинные данные](evidence.json) сохраняют фактические исходы и counts.
Skips не доказывают реализацию. Проверки новых kernels отдельно выполняются
в Actions под Python 3.11/3.12 и публикуют `notebook-kernel.json`.

Воспроизведение из корня репозитория в новый output directory:

```bash
python -m scripts.notebook_execution_evidence --output work/notebook-evidence
```

Training execution — отдельная реализация в issue #81. Этот интерфейс
отказывает при недоступном training runner до создания output.

Локальная проверка: [930-pass PostgreSQL JUnit](junit.xml), [55-pass targeted JUnit](pr93-unit.xml), [фактический новый Python 3.12 kernel](kernel12.json). Нет failures/errors/skips; input/report provenance сохранён в manifests. Проверка Python 3.11/3.12 в Actions публикует собственный kernel result с фактическим source provenance.
