#!/usr/bin/env bash
# Build PhyML (serial) and PhyML-MPI (OpenMPI) from a source tarball.
# Usage: build_phyml_linux.sh <phyml-src.tar.gz> <dest>
# Needs: build-essential autoconf automake libtool pkg-config libopenmpi-dev
set -euo pipefail

src_archive=$(readlink -f "$1")
dest=$(mkdir -p "$2" && readlink -f "$2")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

tar -xzf "$src_archive" -C "$work"
cd "$work"/phyml-*

# configure.ac compiles with -march=native: a binary built on the CI runner dies with
# SIGILL on an older CPU. x86-64-v2 (SSE4.2, every x86-64 CPU since about 2009) keeps
# PhyML's SSE likelihood code; --disable-native would drop vectorisation altogether.
sed -i 's/-march=native/-march=x86-64-v2/; s/-mcpu=native/-march=x86-64-v2/' configure.ac

# the release tarball ships a stale configured tree: regenerate from scratch
make distclean >/dev/null 2>&1 || true
sh ./autogen.sh

no_native() {
  if grep -rq -e '-march=native' -e '-mcpu=native' --include=Makefile .; then
    echo 'build_phyml_linux.sh: -march=native is still in the Makefiles' >&2
    exit 1
  fi
}

# Single-threaded make: parallel builds crashed GCC (internal compiler error
# in evolve.c) on Ubuntu 26.04; -j1 is reliable everywhere.
./configure --enable-phyml
no_native
make -j1
install -m 755 src/phyml "$dest/phyml"

make distclean >/dev/null
./configure --enable-phyml-mpi
no_native
make -j1
install -m 755 src/phyml-mpi "$dest/phyml-mpi"

echo "built: $dest/phyml $dest/phyml-mpi"
