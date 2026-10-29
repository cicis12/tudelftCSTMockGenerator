#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
command -v pdftotext >/dev/null || { echo 'Install Poppler (pdftotext) first.' >&2; exit 1; }
mkdir -p context/extracted
for file in sources/*.pdf; do
  pdftotext -layout "$file" "context/extracted/$(basename "$file" .pdf).txt"
done
