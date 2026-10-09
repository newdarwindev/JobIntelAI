"""Check generated authored fixtures without overwriting the repository's data."""

from pathlib import Path
from tempfile import TemporaryDirectory

from build_synthetic_dataset import main as build_dataset

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory(prefix="jobintel-fixtures-") as directory:
        generated = Path(directory)
        build_dataset(generated)
        files = sorted(
            path.relative_to(generated) for path in generated.rglob("*") if path.is_file()
        )
        for relative in files:
            committed = ROOT / "data" / relative
            if (
                not committed.is_file()
                or committed.read_bytes() != (generated / relative).read_bytes()
            ):
                raise SystemExit(f"Fixture drift: data/{relative}. Rebuild and review the change.")
        committed_files = {
            path.relative_to(ROOT / "data") for path in (ROOT / "data").rglob("*") if path.is_file()
        }
        reviewed = Path("evaluation/reviewed-v1.json")
        if committed_files != set(files) | {reviewed}:
            raise SystemExit(
                "Unexpected files in public data/: review ownership and fixture inventory."
            )
        print(f"Verified {len(files)} authored fixture files without modifying data/.")
        from jobintel.evaluation_corpus import load_reviewed

        corpus = load_reviewed(ROOT / "data")
        print(f"Verified {len(corpus.cases)} frozen source-reviewed annotations.")


if __name__ == "__main__":
    main()
