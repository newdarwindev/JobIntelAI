"""Portable experiments on the pinned source-reviewed evaluation benchmark."""

from pydantic import model_validator

from jobintel.evaluation_corpus import ReviewedCorpus, load_reviewed
from jobintel.experiment_corpus import FrozenCase, FrozenCorpus, read_json
from jobintel.snapshots import content_hash


class ReviewedExperimentCorpus(FrozenCorpus):
    reviewed: ReviewedCorpus

    @model_validator(mode="after")
    def aligned_review(self):
        expected = [
            FrozenCase(
                case_id=c.case_id, text=c.text, snapshot_sha256=c.snapshot_sha256, gold=c.gold
            )
            for c in self.reviewed.cases
        ]
        if self.cases != expected or self.review != self.reviewed.review:
            raise ValueError("experiment snapshots/labels must match the reviewed benchmark")
        from jobintel.experiment_corpus import digest

        if self.reviewed.taxonomy_sha256 != digest(self.taxonomy):
            raise ValueError("experiment taxonomy must match the reviewed benchmark")
        return self


def freeze_reviewed(root):
    corpus = load_reviewed(root)
    return ReviewedExperimentCorpus(
        revision=corpus.revision,
        public=True,
        review=corpus.review,
        source_labels_sha256=content_hash((root / "evaluation/reviewed-v1.json").read_text()),
        taxonomy=read_json(root / "taxonomy.json"),
        cases=[
            FrozenCase(
                case_id=c.case_id, text=c.text, snapshot_sha256=c.snapshot_sha256, gold=c.gold
            )
            for c in corpus.cases
        ],
        reviewed=corpus,
    )


def public_reference(corpus, root):
    from jobintel.experiment_corpus import freeze_bundled

    return (
        freeze_reviewed(root)
        if isinstance(corpus, ReviewedExperimentCorpus)
        else freeze_bundled(root)
    )
