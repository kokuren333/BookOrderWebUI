#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$(uname -s):$(uname -m)" in
  Darwin:arm64) TARGET=macos-arm64 ;;
  Darwin:x86_64) TARGET=macos-x64 ;;
  Linux:x86_64) TARGET=linux-x64 ;;
  Linux:aarch64|Linux:arm64) TARGET=linux-arm64 ;;
  *) echo 'Unsupported OS/CPU for this portable runtime.' >&2; exit 1 ;;
esac
EXPECTED=$(cat "$ROOT/runtime/target.txt")
case "$TARGET" in
  macos-*) if [ "$(sw_vers -productVersion | cut -d . -f 1)" -lt 15 ]; then echo 'Bundled Pandoc requires macOS 15 or later.' >&2; exit 1; fi ;;
esac
if [ "$TARGET" != "$EXPECTED" ]; then
  echo "This job is for $EXPECTED, but this machine is $TARGET. Download the matching job." >&2
  exit 1
fi
ARCHIVE="$ROOT/runtime/archives/python.tar.gz"
if command -v sha256sum >/dev/null 2>&1; then
  HASH=$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)
else
  HASH=$(shasum -a 256 "$ARCHIVE" | cut -d ' ' -f 1)
fi
if [ "$HASH" != "$(cat "$ROOT/runtime/python.sha256")" ]; then
  echo 'Python archive checksum mismatch.' >&2; exit 1
fi
if [ ! -x "$ROOT/runtime/python/bin/python3" ]; then
  mkdir -p "$ROOT/runtime/python"
  tar -xzf "$ARCHIVE" -C "$ROOT/runtime/python" --strip-components=1
fi
export PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1
exec "$ROOT/runtime/python/bin/python3" "$ROOT/scripts/bootstrap.py" "${1:-check}"
