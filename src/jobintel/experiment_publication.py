"""Public report publication requires pinned authored inputs and a hash-bound audit."""

import json
import re
from datetime import UTC, datetime

from pydantic import Field, field_validator

from jobintel.experiment_corpus import digest, parse_corpus, read_json, verify_public, write_json
from jobintel.experiment_reviewed import public_reference
from jobintel.experiments import ExperimentSpec, rescore
from jobintel.schemas import StrictModel


class PublicationAudit(StrictModel):
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    corpus_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str = Field(min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=2000)
    revision: str = Field(min_length=1, max_length=200)
    reviewed_at: datetime
    approved: bool = Field(default=False, strict=True)
    findings: list[str] = Field(default_factory=list)

    @field_validator("reviewed_at")
    @classmethod
    def timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("review timestamp requires a timezone")
        return value


def public_checks(report, root):
    corpus = parse_corpus(report["corpus"])
    verify_public(corpus, public_reference(corpus, root))
    scores = rescore(report)
    if [r["summary"] for r in report["results"]] != [r["summary"] for r in scores["results"]]:
        raise ValueError("stored summaries differ from reproduced scoring")
    # This catches recognizable secret forms; the required reviewer checks all output text.
    check_credentials(report)
    return corpus


def check_credentials(value):
    encoded = json.dumps(value, ensure_ascii=False)
    if re.search(r"sk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+|-----BEGIN .*PRIVATE KEY-----", encoded):
        raise ValueError(
            "publication contains a recognizable credential; retain private diagnostics"
        )


def audit_draft(report, root):
    public_checks(report, root)
    return PublicationAudit(
        report_sha256=digest(report),
        corpus_sha256=report["corpus_sha256"],
        reviewer="pending",
        method="pending source/output/privacy and per-case metric review",
        revision="pending",
        reviewed_at=datetime.now(UTC),
        findings=[
            "Review every prediction, raw output and failure; record trade-offs, limitations and reviewer identity before approval."
        ],
    ).model_dump(mode="json")


def publish_live(args, report, corpus):
    from jobintel.config import fixture_root

    public_checks(report, fixture_root())
    from jobintel.experiments import plan

    plan(corpus, ExperimentSpec.model_validate(report["spec"]), report["mode"])
    if report["mode"] != "live" and args.readme:
        raise ValueError("network evidence cannot replace the authorized hosted README results")
    if report.get("format_version") != 2 or not args.audit:
        raise ValueError("live publication requires a format-v2 report and separate reviewer audit")
    audit = PublicationAudit.model_validate(read_json(args.audit))
    if (
        not audit.approved
        or audit.findings
        or "pending" in {audit.reviewer, audit.revision}
        or audit.method.startswith("pending")
    ):
        raise ValueError("live publication requires a completed approved reviewer audit")
    if audit.report_sha256 != digest(report) or audit.corpus_sha256 != report["corpus_sha256"]:
        raise ValueError("reviewer audit does not describe this exact report")
    if audit.reviewed_at < datetime.fromisoformat(report["completed_at"]):
        raise ValueError("reviewer audit predates the completed report")
    check_credentials(audit.model_dump(mode="json"))
    readme = prepare_readme(report, args.output, args.readme) if args.readme else None
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "report.json", report)
    write_json(args.output / "scores.json", rescore(report))
    write_json(args.output / "audit.json", audit.model_dump(mode="json"))
    publish_configurations(args.output, report)
    (args.output / "comparison.md").write_text(comparison(report), encoding="utf-8")
    if args.readme:
        args.readme.write_text(readme, encoding="utf-8")
    print(
        f"Audited {report['mode']} report published to {args.output}; failures remain in the comparison."
    )
    return 0


def publish_configurations(output, report):
    write_json(output / "corpus.json", report["corpus"])
    scored = rescore(report)["results"]
    for result, scores in zip(report["results"], scored, strict=True):
        write_json(
            output / f"configuration-{result['configuration']}.json",
            {
                "format_version": 2,
                "mode": report["mode"],
                "created_at": report["created_at"],
                "report_sha256": digest(report),
                "corpus_sha256": report["corpus_sha256"],
                "corpus_file": "corpus.json",
                "spec": report["spec"],
                "spec_sha256": report["spec_sha256"],
                "provenance": report["provenance"],
                "schema_sha256": report["schema_sha256"],
                "result": {**result, "summary": scores["summary"]},
            },
        )


def prepare_readme(report, output, path):
    prefix = output.resolve().relative_to(path.resolve().parent).as_posix()
    body = comparison(report)
    for target in [
        "report.json",
        "scores.json",
        "audit.json",
        *(f"configuration-{r['configuration']}.json" for r in report["results"]),
    ]:
        body = body.replace(f"]({target})", f"]({prefix}/{target})")
    start, end = "<!-- LIVE-EXPERIMENTS:START -->", "<!-- LIVE-EXPERIMENTS:END -->"
    original = path.read_text(encoding="utf-8")
    section = start + "\n\n## Разрешённые live-измерения\n\n" + body + "\n" + end
    if start not in original and end not in original:
        return original.rstrip() + "\n\n" + section + "\n"
    if (
        original.count(start) != 1
        or original.count(end) != 1
        or original.index(start) >= original.index(end)
    ):
        raise ValueError("README has invalid live-experiment markers")
    return original[: original.index(start)] + section + original[original.index(end) + len(end) :]


def metric(value):
    return "нет данных" if value is None else f"{value:.4f}"


def comparison(report):
    spec = report["spec"]
    lines = [
        f"Режим эксперимента: {report['mode']}; запрошенная модель: {spec['model']}.",
        f"Создан: {report['created_at']}; SHA-256 корпуса: `{report['corpus_sha256']}`.",
        f"SHA-256 конфигурации: `{report['spec_sha256']}`. [Полный отчёт](report.json); [Повторно подсчитанные метрики](scores.json).",
        "",
        "| Конфигурация | Успех / случаи | Ошибки | Precision | Recall | Тип | Цитата | Неподтверждённые claims | Верный unknown | Секунды на вакансию | Tokens вход/выход | Стоимость USD |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for result in rescore(report)["results"]:
        summary = result["summary"]
        metrics = summary["metrics"] or {}
        tokens = summary["tokens"]
        usage = f"{tokens['input']}/{tokens['output']}" if tokens else "нет данных"
        values = [
            metric(metrics.get(k))
            for k in [
                "precision",
                "recall",
                "type_accuracy",
                "evidence_accuracy",
                "semantic_hallucination_rate",
                "abstention_quality",
            ]
        ]
        name = result["configuration"]
        label = f"[{name}](configuration-{name}.json)" if report["mode"] != "fake" else name
        lines.append(
            f"| {label} | {summary['succeeded']}/{len(report['corpus']['cases'])} | {summary['failed']} | "
            + " | ".join(values)
            + f" | {summary['elapsed_seconds']:.4f} | {usage} | {metric(summary['cost_usd'])} |"
        )
    lines.extend(
        [
            "",
            "Метрики относятся к успешным случаям; ошибки и исходные ответы сохранены в полном отчёте. Matching использует gold-требования и подтверждённые сведения кандидата. Нулевые знаменатели и неизмеренные usage/cost/LLM latency остаются неизвестными.",
        ]
    )
    if spec["pricing"]:
        lines.append(
            "Датированная оценка стоимости, не сверка списаний: "
            + json.dumps(spec["pricing"], sort_keys=True)
        )
    if report["mode"] == "fake":
        lines.append(
            "Регрессия fake provider: качество live-модели и оплаченный usage не измеряются. Исходные fixture-ответы одинаковы в A/B/C, только C применяет normalization."
        )
    elif report["mode"] == "emulator":
        lines.append(
            "Авторская проверка сетевого контракта: без inference, качества модели, tokens и оплаченной стоимости. [Аудит output](audit.json)."
        )
    elif report["mode"] == "local-inference":
        lines.append(
            "Измерена закреплённая локальная CPU-модель на выбранных reviewed snapshots. B/C используют одинаковую source-bound Chat grammar и отдельные вызовы; только C нормализует. Это не hosted benchmark или измерение оплаченной стоимости. [Аудит output](audit.json)."
        )
    else:
        lines.append(
            "B и C используют отдельные запросы с одинаковыми prompts/snapshots; вариативность ответов мешает приписать разницу normalization. [Аудит](audit.json) проверяет output/privacy отдельно от source-label review."
        )
    lines.extend(error_analysis(report))
    return "\n".join(lines) + "\n"


def error_analysis(report):
    lines = []
    for result in report["results"]:
        for record in result["records"]:
            if record["error_code"]:
                lines.append(
                    f"- {result['configuration']} / {record['case_id']}: {record['error_code']}"
                )
        for detail in result["summary"].get("reviewed_per_case") or []:
            rate = detail["reviewed_metrics"]["semantic_unsupported_claim_rate"]
            if rate["numerator"]:
                lines.append(
                    f"- {result['configuration']} / {detail['case_id']}: {rate['numerator']}/{rate['denominator']} claims не подтверждены source-review; сравните исходные predictions с frozen gold и обоснованием источника."
                )
    return lines
