#!/usr/bin/env bash
# Pin the workflow linter and verify the upstream release checksum before execution.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  printf 'This installer supports Linux x86_64; install actionlint 1.7.7 for your platform.\n' >&2
  exit 1
fi
version=1.7.7
archive="actionlint_${version}_linux_amd64.tar.gz"
release="https://github.com/rhysd/actionlint/releases/download/v${version}"
download_dir=$(mktemp -d)
trap 'rm -rf "$download_dir"' EXIT
curl --fail --location --silent --show-error "$release/$archive" -o "$download_dir/$archive"
curl --fail --location --silent --show-error "$release/actionlint_${version}_checksums.txt" \
  -o "$download_dir/checksums.txt"
(cd "$download_dir" && sha256sum --check --ignore-missing checksums.txt)
mkdir -p local_data/bin
tar -xzf "$download_dir/$archive" -C local_data/bin actionlint
local_data/bin/actionlint -version
