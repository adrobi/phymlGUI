# Spike: native Windows build of RAxML-NG 2.0.3

**Question.** Can RAxML-NG be built as a self-contained native `raxml-ng.exe`
for Windows x64, producing the same results as the official Linux binary?

**Answer: yes.** With 4 configure flags and a 167-line patch (11 files), the
build is self-contained (imports only `KERNEL32` + the Universal CRT that ships
with Windows 10/11) and reproduces the official Linux binary bit for bit on
everything driven by the RNG, and to 1e-4 log-units after numerical
optimization. The exe built during the spike is **throwaway**; the deliverable
is the recipe + patch below, to be reproduced in CI (release sub-project).

Upstream has no Windows binaries (Linux/macOS + source only; Windows users are
pointed to WSL), so this is the only way to ship RAxML-NG in a
"unzip and run" phymlGUI release.

## Recipe

- Sources: `raxml-ng_v2.0.3_source.zip` from the official GitHub release,
  SHA256 `7cd3fa6b1de373777d688032c9ec6731078b67e6a812d7a1d779295d016843d2`
- Toolchain: MSYS2 **UCRT64** — `mingw-w64-ucrt-x86_64-{gcc,cmake,ninja}`
  (tested with GCC 16.2.0, CMake 4.4.4, Ninja 1.13.2)
- Patch: `git apply -p1 raxml-ng-2.0.3-windows.patch` (from the source root)
- Configure + build:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DSTATIC_BUILD=ON -DPORTABLE_BUILD=ON -DCORAX_BUILD_PORTABLE_ARCH=x86-64 \
  -DUSE_MPI=OFF "-DCMAKE_CXX_FLAGS=-D_USE_MATH_DEFINES -D_GNU_SOURCE"
cmake --build build -j
```

## What had to change, and why

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `-march=` with empty value | portable build needs `CORAX_BUILD_PORTABLE_ARCH`; its default is commented out | configure flag `x86-64` (SIMD kernels still dispatched at runtime) |
| 2 | `thread-local variable declared as dllexport` | `CORAX_EXPORT` is `dllexport` on Windows even for the static lib | export only when `CORAX_SHARED` is defined |
| 3 | `M_PI` undeclared | MinGW hides math constants in strict C++ mode | `-D_USE_MATH_DEFINES` |
| 4 | `asprintf` undeclared | g++ predefines `_GNU_SOURCE` on Linux only | `-D_GNU_SOURCE` |
| 5 | `std::max(unsigned long, size_t)` | LLP64: `long` is 32-bit on Windows | `std::max<size_t>` |
| 6 | `sys/resource.h`, `sysconf`, `sysinfo`, `realpath`, `posix_memalign`, `u_int32_t` missing | POSIX-only APIs in `sysutil.cpp` | Win32 equivalents (`GetProcessTimes`, `GetProcessMemoryInfo`, `GlobalMemoryStatusEx`, `_fullpath`, `_aligned_malloc`); `uint32_t` |
| 7 | RAM/peak memory silently truncated to 32 bits | `unsigned long` return type (feeds thread/worker limits) | `unsigned long long` |
| 8 | **Segfault** building the first parsimony tree | `corax_random_r` yields [0, 2^31-1] but was normalized by `RAND_MAX` (32767 on Windows) → out-of-bounds index in the Fisher–Yates shuffle | normalize by 2^31-1 |
| 9 | **Heap corruption** (`c0000374`) on exit of a tree search | `_aligned_malloc` memory freed with `free()` (legal on POSIX, not on Windows) — 5 sites; plus 1 reverse case (`malloc` → `corax_aligned_free`) | matching free in all 6 places (found by a scripted audit of all 84 aligned allocations) |
| 10 | **16 duplicate replicates out of 1000** in bootstrap; results differ from Linux for the same `--seed` | per-tree/per-replicate seeds come from `rand()`, a 15-bit LCG on Windows | `raxml_rand()`/`raxml_srand()`: glibc-identical generator from coraxlib on Windows, plain `rand`/`srand` elsewhere |

Fixes 8–10 are silent-correctness issues: a build that merely compiles would
crash, corrupt memory, or quietly produce non-independent bootstrap replicates.

## Verification against the official Linux binary (WSL, same arguments, `--seed 42`)

| Check | Result |
|---|---|
| ML search, synthetic nt (8 taxa) | lnL identical, RF 0 |
| ML search, real CytB mammals | RF 0, \|ΔlnL\| = 9e-5 (libm differences during optimization) |
| ML search, synthetic protein (LG+G) | lnL identical, RF 0 |
| Fixed tree + fixed model, no optimization (nt and aa) | lnL identical — likelihood kernels match |
| `--all`, 50 bootstraps, 4 threads | 50/50 replicate trees identical, supports identical |
| Bootstrap MSAs, 1000 replicates | 1000/1000 identical to Linux, 0 duplicates (was 16) |
| Parsimony / random starting trees | identical |

## Open points for the release sub-project

- Reproduce the build in GitHub Actions (MSYS2 is preinstalled on
  `windows-latest`) and keep the Linux-vs-Windows comparison as a regression job.
- Not exercised yet: partitioned analyses, checkpoint/restart, `--terrace`
  (terraphast/GMP disabled), very large alignments (> 4 GB RAM).
- License: RAxML-NG is **AGPL-3.0** — the release must ship (or link to) the
  exact sources plus this patch.
- The fixes are upstreamable (mostly `#ifdef _WIN32` or platform-neutral);
  sending them upstream is optional and outward-facing, so it needs a separate
  decision.
