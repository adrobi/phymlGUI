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

# the release tarball ships a stale configured tree: regenerate from scratch
make distclean >/dev/null 2>&1 || true
sh ./autogen.sh

# no --enable-native: the binaries must run on any x86-64 CPU.
# Single-threaded make: parallel builds crashed GCC (internal compiler error
# in evolve.c) on Ubuntu 26.04; -j1 is reliable everywhere.
./configure --enable-phyml
make -j1
install -m 755 src/phyml "$dest/phyml"

make distclean >/dev/null
./configure --enable-phyml-mpi
make -j1
install -m 755 src/phyml-mpi "$dest/phyml-mpi"

echo "built: $dest/phyml $dest/phyml-mpi"
