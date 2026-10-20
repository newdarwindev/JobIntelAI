# Общий запуск для ноутбуков

Ноутбуки и CLI используют `jobintel.notebook_runs`: одинаковые параметры,
предварительные проверки и существующий experiment scorer, без отдельной базы.
Коллекция ноутбуков и Binder отслеживаются в [#57](https://github.com/newdarwindev/JobIntelAI/issues/57).

Из корня checkout установите лёгкую среду без весов и training framework:

```bash
python -m pip install -c requirements.lock.txt -c requirements-notebooks.lock.txt -e '.[notebooks]'
```

`requirements.lock.txt` закрепляет приложение и инструменты разработки,
`requirements-notebooks.lock.txt` добавляет kernel/nbclient/nbformat и совместимые
транзитивные зависимости. Для разработки добавьте `dev` к списку extras.
Training framework и его отдельный lock выбираются вместе с рецептом в #81;
установка notebook extra не запускает обучение и не скачивает модель.

Сохраните JSON-параметры, например в игнорируемом `local_data/notebook.json`:

```json
{"mode":"fixture","dataset":"fixture","split":"regression","output":"work/notebook-first"}
```

```bash
jobintel notebook plan --config local_data/notebook.json
jobintel notebook run --config local_data/notebook.json
jobintel notebook verify --manifest work/notebook-first/manifest.json
```

`plan` проверяет входы без создания output, provider, базы или контейнера.
`run` требует нового каталога; повторное использование отказывается перезаписывать
результаты. CLI возвращает 2 при отказе preflight, 1 при ошибках/прерывании запуска
и 0 для успешного запуска/плана. Ошибки вывода содержат ограниченный код, а не
значения отклонённых параметров или exception body.

| Режим | Поведение |
| --- | --- |
| `fixture` | Существующий fake experiment на публичных pinned fixtures; не измеряет LLM quality |
| `saved-report` | Проверка и точный rescore `report` без provider; исходный отчёт не меняется и не копируется |
| `local-inference` | Только явно заданный scoped HTTP endpoint уже работающего pinned runtime; без запуска сервиса и без fallback |
| `training` | Типизированный зарезервированный режим; отказ `training_runner_unavailable_issue_81` до выделения ресурсов |

В Python передайте тот же объект, без CLI subprocess:

```python
from pathlib import Path
from jobintel.notebook_contracts import NotebookRequest
from jobintel.notebook_runs import run_notebook

manifest = run_notebook(NotebookRequest(output=Path("work/notebook-python")))
```

Для `saved-report` задайте `report`; для reviewed-корпуса также явно задайте
`dataset="reviewed", split="development"`. Доступны старые experiment reports v1/v2:
их форматы и смысл метрик не меняются. Исторический публичный v1 corpus допускается
по точному закреплённому hash; произвольный `public=true` не разрешает публикацию.

Для local inference задайте reviewed selection, `endpoint`, `spec` с B/C,
точной моделью из runtime, `max_input_tokens=6144`, `max_output_tokens=2048`
и достаточным `max_calls`. Используются существующий planner и строгая проверка
model/context. Параметр `timeout_seconds` ограничивает HTTP-вызов (1–600), а не
полное время эксперимента. Поддерживаемый local seed — 42; fixtures детерминированы,
seed не превращает replay в новую генерацию. Новые train/test splits требуют #78/#79.

`manifest.json` — отдельная версия envelope, а не новая версия scorer. В нём есть
execution/evidence modes, outcome, source/config/data hashes, null для неизвестных
данных и относительные имена/размеры/SHA-256 outputs. `verify` проверяет envelope,
parameters и файлы, запрещая выход за каталог. Checksum не является подписью,
review или разрешением публикации; используйте существующий output audit.
При прерывании остаются manifest и незавершённый experiment checkpoint. Resume
этого checkpoint выполняется существующим experiment CLI, с его ограничениями.

Проверка в новом kernel с запрещёнными database/HTTP вызовами:

```bash
python -m scripts.notebook_kernel_smoke --output work/notebook-kernel.json
```

Здесь используется только публичный corpus. Настройки inherited provider/database
не выбирают другую модель или приватную базу; `data_root` задаётся явно и по
умолчанию равен `data/` в checkout. Private corpus outputs остаются в `local_data/`.

CI для Python 3.11/3.12 устанавливает отдельно закреплённый notebook extra после backend checks и выполняет `python -m scripts.notebook_kernel_smoke`. Новый kernel проверяет fixture, точный saved rescore и preflight refusal с запрещёнными database/HTTP вызовами. Фактические результаты и source provenance сохраняются в `work/ci/notebook-kernel.json`; обучение и model weights не выделяются.
