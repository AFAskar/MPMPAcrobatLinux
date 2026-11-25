#!/usr/bin/env bash
set -euo pipefail

# Build an x86_64 RPM package from a compiled release binary + pinned PDFium.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${1:-$(awk -F'"' '/^version =/{print $2; exit}' "$ROOT/Cargo.toml")}"
BIN="${2:-$ROOT/target/release/mpmb-reader}"
OUT_DIR="${3:-$ROOT/output/dist}"
PDFIUM_DIR="${PDFIUM_DIR:-$ROOT/output/deps}"

if [[ ! -x "$BIN" ]]; then
  echo "Release binary not found at $BIN. Run: cargo build --release --locked -j 1" >&2
  exit 1
fi
if [[ ! -f "$PDFIUM_DIR/lib/libpdfium.so" ]]; then
  echo "PDFium not found at $PDFIUM_DIR/lib/libpdfium.so. Run: tools/native/setup-pdfium" >&2
  exit 1
fi

TOPDIR="$(mktemp -d)"
trap 'rm -rf "$TOPDIR"' EXIT
mkdir -p "$TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

LICENSE_FILE="$PDFIUM_DIR/LICENSE"
if [[ ! -f "$LICENSE_FILE" ]]; then
  LICENSE_FILE="$TOPDIR/LICENSE-PDFIUM.txt"
  echo "PDFium (Chromium BSD-3-Clause)" > "$LICENSE_FILE"
fi

LICENSES_DIR="$PDFIUM_DIR/licenses"
if [[ ! -d "$LICENSES_DIR" ]]; then
  LICENSES_DIR="$TOPDIR/empty-licenses"
  mkdir -p "$LICENSES_DIR"
fi

# RPM version cannot contain hyphens; convert pre-release hyphens to tildes.
RPM_VERSION="${VERSION//-/\~}"

rpmbuild -bb \
  --define "_topdir $TOPDIR" \
  --define "_version $RPM_VERSION" \
  --define "_binary_path $BIN" \
  --define "_pdfium_lib $PDFIUM_DIR/lib/libpdfium.so" \
  --define "_pdfium_license $LICENSE_FILE" \
  --define "_pdfium_licenses_dir $LICENSES_DIR" \
  --define "_assets_dir $ROOT/packaging/assets" \
  "$ROOT/packaging/rpm/mpmb-reader.spec"

mkdir -p "$OUT_DIR"
RPM_BUILT="$(find "$TOPDIR/RPMS" -name '*.rpm' -print -quit)"
OUT_FILE="$OUT_DIR/mpmb-reader-${VERSION}-1.x86_64.rpm"
cp "$RPM_BUILT" "$OUT_FILE"
echo "Built RPM: $OUT_FILE"
