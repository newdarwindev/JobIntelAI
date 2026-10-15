import {readFile,writeFile} from 'node:fs/promises';

const header=(e,title,file)=>[
  `# ${title}`,'',
  `Источник: ${e.origin==='github-actions'?`[Запуск GitHub Actions](${e.run_url})`:'локальный Playwright'} · проверенный коммит \`${e.git_sha}\`.`,
  `SHA-256 исходного содержимого: \`${e.source_hash}\`. [Машинные наблюдения](${file}).`,'',
  'Авторский synthetic ввод, реальные API/БД; платные hosted запросы не выполнялись. Эти проверки не измеряют качество модели.','',
];
const display=value=>value===null||value===undefined?'Не перечислено':String(value);
export function mutationMarkdown(e){
  const rows=e.rows.map(r=>`| ${r.project} | ${r.kind} | ${r.scenario} | ${r.initial_state} → ${r.final_state} | ${r.browser_post_requests} | ${r.api_conflict_probes??0} | ${r.completed_handler_executions} | ${display(r.before_records)} → ${display(r.after_records)} | ${r.saved_id??'Новый результат не сохранён'} |`);
  return [...header(e,'Восстановление mutations: измеренные наблюдения','mutation-comparison.json'),
    'Каждая строка получена из успешного UI13: наблюдаемые browser requests, lookup сохранённой операции и API history/catalogues. Потеря до доставки даёт два POST с одним key, после commit — восстановление чтением. Отдельный conflicting-body probe возвращает 409. Completed handler executions не равны числу upstream requests или retries.','',
    'Snapshot/extraction/registry/revision/evaluation counts взяты из API. У matching нет каталога: число rows явно неизвестно, вместо него проверяются точный saved match ID и immutable response. Integration tests считают domain records напрямую. Unsent cancellation и validation rejection не запускают handler. Восстановление display/status не добавляет POST/run.','',
    '| Viewport | Mutation | Граница потери | Исход | Browser POST | Conflicting probes | Завершённые handlers | Записей до → после | Точный saved ID |',
    '| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |',...rows,'',
    '[Desktop UI13](../../ui-recordings/UI13-desktop-chromium.webm) · [Mobile UI13](../../ui-recordings/UI13-mobile-chromium.webm)','',
    'Прежние snapshots/extractions/revisions/matches/evaluations прочитаны без изменений. In-flight case использует отдельный Responses emulator и bounded delay. Unknown outcome остаётся uncertain до подтверждения lookup, без повторного execution. Browser storage хранит только opaque operation ID.',''].join('\n');
}
const counts=v=>`${v.completed} завершено / ${v.failed} ошибок / ${v.unattempted} не начато / ${v.uncertain} неизвестно`;
export function batchMarkdown(e){
  const rows=e.rows.map(r=>`| ${r.project} | ${r.kind} | ${r.scenario} | ${r.before.registered}/${r.before.current_extracted} | ${counts(r.partial.counts)} | ${r.partial.server?`${r.partial.server.registered}/${r.partial.server.current_extracted}`:'Нет данных'} | ${counts(r.resumed.counts)} | ${r.resumed.server.registered}/${r.resumed.server.current_extracted} | ${r.browser_mutation_posts.length} | ${r.partial.items.filter(i=>i.state==='completed').map(i=>`${i.jobId}: ${i.resultId}`).join('<br>')||'До прерывания завершённых items нет'} |`);
  return [...header(e,'Batches: измеренные исходы до, после ошибки и продолжения','batch-comparison.json'),
    'UI14 выбирает три authored jobs через обозначенный fixture-metadata read; snapshots/extraction/matching используют настоящие API. Unsupported fixture source и реальный stale extraction вызывают ошибки, успешные domain responses не подменяются. UI03/UI05 также проходят все 20 jobs, unit gate проверяет continuation bound на 45 items.','',
    'Completed items сохраняют точные result/attempt IDs при continuation: нет повторного POST или повторной успешной extraction/match. Before-delivery retry сохраняет key, post-commit lookup/reload не добавляет mutation. Явный replan меняет только unfinished items; другая candidate revision блокирует matching до восстановления captured selection. Empty batch ничего не отправляет.','',
    'Это counts captured batch и сервера, не качество модели. In-flight journal остаётся uncertain до доставки даже при server commit. Browser POST counts учитывают keyed snapshot/extract/match, исключая registry preparation, reads, profiles и независимую fault injection. У matching нет каталога: проверяются saved responses и operation IDs. Исходная extraction history сохранена.','',
    '| Viewport | Batch | Граница | До: зарегистрировано/извлечено | Частичные исходы | Частичный сервер | После continuation | Итоговый сервер | Browser POST | Сохранённые completed IDs |',
    '| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |',...rows,'',
    '[Desktop UI14](../../ui-recordings/UI14-desktop-chromium.webm) · [Mobile UI14](../../ui-recordings/UI14-mobile-chromium.webm)','',
    'Панель сохраняет identities/states и prior rejected operation IDs при navigation/reload. Session storage содержит только IDs/config/selection/states, bodies и error messages читаются в память. Unknown operation блокирует continuation. Каждый exit пытается обновить authoritative state; failure обозначен как отсутствие данных.',''].join('\n');
}
if(process.argv.includes('--saved')){
  for(const [file,render] of [['docs/issue-evidence/40/mutation-comparison',mutationMarkdown],['docs/issue-evidence/41/batch-comparison',batchMarkdown]]){
    const evidence=JSON.parse(await readFile(`${file}.json`,'utf8'));
    await writeFile(`${file}.md`,render(evidence));
  }
}
