#!/usr/bin/env bash
set -euo pipefail

# Build a single-file .flatpak bundle from a compiled release binary + pinned PDFium.
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

FONT_SRC="${MPMB_FONT:-}"
if [[ -z "$FONT_SRC" ]]; then
  for candidate in \
    /usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf \
    /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
    /usr/share/fonts/TTF/DejaVuSans.ttf \
    "$PDFIUM_DIR/fonts/DejaVuSans.ttf"; do
    if [[ -f "$candidate" ]]; then
      FONT_SRC="$candidate"
      break
    fi
  done
fi
if [[ -z "$FONT_SRC" || ! -f "$FONT_SRC" ]]; then
  echo "DejaVuSans.ttf not found; install dejavu-sans-fonts or set MPMB_FONT." >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp "$ROOT/packaging/flatpak/io.github.afaskar.MpmbReader.yml" "$STAGE/"
cp "$BIN" "$STAGE/mpmb-reader"
cp "$PDFIUM_DIR/lib/libpdfium.so" "$STAGE/libpdfium.so"
if [[ -f "$PDFIUM_DIR/LICENSE" ]]; then
  cp "$PDFIUM_DIR/LICENSE" "$STAGE/LICENSE-PDFIUM.txt"
else
  echo "PDFium (Chromium BSD-3-Clause)" > "$STAGE/LICENSE-PDFIUM.txt"
fi
mkdir -p "$STAGE/licenses"
if [[ -d "$PDFIUM_DIR/licenses" ]]; then
  cp -r "$PDFIUM_DIR/licenses/." "$STAGE/licenses/"
fi
cp "$FONT_SRC" "$STAGE/DejaVuSans.ttf"
cp "$ROOT/packaging/assets/LICENSE-DEJAVU.txt" "$STAGE/LICENSE-DEJAVU.txt"
cp "$ROOT/packaging/assets/io.github.afaskar.MpmbReader.desktop" "$STAGE/"
cp "$ROOT/packaging/assets/io.github.afaskar.MpmbReader.metainfo.xml" "$STAGE/"
cp "$ROOT/packaging/assets/io.github.afaskar.MpmbReader.svg" "$STAGE/"

mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/mpmb-reader-${VERSION}-x86_64.flatpak"

flatpak-builder --force-clean --user --repo="$STAGE/repo" \
  "$STAGE/build-dir" \
  "$STAGE/io.github.afaskar.MpmbReader.yml"

flatpak build-bundle "$STAGE/repo" "$OUT_FILE" io.github.afaskar.MpmbReader
echo "Built Flatpak bundle: $OUT_FILE"
