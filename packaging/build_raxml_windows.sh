#!/usr/bin/env bash
# Build a native, self-contained raxml-ng.exe (Windows x64) from the official
# source zip with the patch from docs/superpowers/spikes/2026-10-24-raxml-ng-windows.
# Run inside MSYS2 UCRT64 (mingw-w64-ucrt-x86_64-{gcc,cmake,ninja}).
# Usage: build_raxml_windows.sh <raxml-ng_v2.0.3_source.zip> <dest>
set -euo pipefail
[ -d /ucrt64/bin ] && export PATH="/ucrt64/bin:/usr/bin:$PATH"

here=$(cd "$(dirname "$0")" && pwd)
src_archive=$(cygpath -u "$1" 2>/dev/null || echo "$1")
dest=$(cygpath -u "$2" 2>/dev/null || echo "$2")
mkdir -p "$dest"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

unzip -q "$src_archive" -d "$work/src"
cd "$work/src"
git apply -p1 --whitespace=nowarn "$here/patches/raxml-ng-2.0.3-windows.patch"

cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DSTATIC_BUILD=ON -DPORTABLE_BUILD=ON -DCORAX_BUILD_PORTABLE_ARCH=x86-64 \
  -DUSE_MPI=OFF "-DCMAKE_CXX_FLAGS=-D_USE_MATH_DEFINES -D_GNU_SOURCE"
cmake --build build -j

install -m 755 build/bin/raxml-ng.exe "$dest/raxml-ng.exe"
echo "built: $dest/raxml-ng.exe"
