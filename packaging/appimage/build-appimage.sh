#!/usr/bin/env bash
set -euo pipefail

# Build a self-contained x86_64 AppImage from a compiled release binary + pinned PDFium.
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

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
APPDIR="$STAGE/MPMB-Reader.AppDir"

mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/lib" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/metainfo" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps" \
  "$APPDIR/usr/share/mpmb-reader/fonts" \
  "$APPDIR/usr/share/licenses/mpmb-reader"

install -Dm755 "$BIN" "$APPDIR/usr/bin/mpmb-reader"
install -Dm644 "$PDFIUM_DIR/lib/libpdfium.so" "$APPDIR/usr/lib/libpdfium.so"
if [[ -f "$PDFIUM_DIR/LICENSE" ]]; then
  install -Dm644 "$PDFIUM_DIR/LICENSE" "$APPDIR/usr/share/licenses/mpmb-reader/LICENSE-PDFIUM.txt"
fi
if [[ -d "$PDFIUM_DIR/licenses" ]]; then
  cp -r "$PDFIUM_DIR/licenses" "$APPDIR/usr/share/licenses/mpmb-reader/licenses"
fi
if [[ -n "$FONT_SRC" && -f "$FONT_SRC" ]]; then
  install -Dm644 "$FONT_SRC" "$APPDIR/usr/share/mpmb-reader/fonts/DejaVuSans.ttf"
fi

install -Dm644 "$ROOT/packaging/assets/io.github.afaskar.MpmbReader.desktop" \
  "$APPDIR/usr/share/applications/io.github.afaskar.MpmbReader.desktop"
install -Dm644 "$ROOT/packaging/assets/io.github.afaskar.MpmbReader.desktop" \
  "$APPDIR/io.github.afaskar.MpmbReader.desktop"
install -Dm644 "$ROOT/packaging/assets/io.github.afaskar.MpmbReader.metainfo.xml" \
  "$APPDIR/usr/share/metainfo/io.github.afaskar.MpmbReader.metainfo.xml"
install -Dm644 "$ROOT/packaging/assets/io.github.afaskar.MpmbReader.svg" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps/io.github.afaskar.MpmbReader.svg"
install -Dm644 "$ROOT/packaging/assets/io.github.afaskar.MpmbReader.svg" \
  "$APPDIR/io.github.afaskar.MpmbReader.svg"
ln -sf io.github.afaskar.MpmbReader.svg "$APPDIR/.DirIcon"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
export MPMB_PDFIUM="${MPMB_PDFIUM:-$HERE/usr/lib/libpdfium.so}"
if [[ -f "$HERE/usr/share/mpmb-reader/fonts/DejaVuSans.ttf" ]]; then
  export MPMB_FONT="${MPMB_FONT:-$HERE/usr/share/mpmb-reader/fonts/DejaVuSans.ttf}"
fi
export LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$HERE/usr/bin/mpmb-reader" "$@"
EOF
chmod 755 "$APPDIR/AppRun"

mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/MPMB-Reader-${VERSION}-x86_64.AppImage"

APPIMAGETOOL="${APPIMAGETOOL:-}"
if [[ -z "$APPIMAGETOOL" ]]; then
  if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="$(command -v appimagetool)"
  else
    APPIMAGETOOL="$STAGE/appimagetool-x86_64.AppImage"
    curl --fail --location --retry 3 \
      "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" \
      -o "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
  fi
fi

ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" --no-appstream "$APPDIR" "$OUT_FILE"
echo "Built AppImage: $OUT_FILE"
