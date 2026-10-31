# Third-party licenses

The release packages bundle these programs unchanged, except RAxML-NG on
Windows, which is built from the official sources with
`packaging/patches/raxml-ng-2.0.3-windows.patch`.

| Program | License | File |
|---|---|---|
| PhyML | GPL-3.0 | `PhyML-COPYING.txt` |
| IQ-TREE 2 | GPL-2.0 | `IQ-TREE-LICENSE.txt` |
| MUSCLE 5 | GPL-3.0 | `MUSCLE-LICENSE.txt` |
| RAxML-NG | AGPL-3.0 | `RAxML-NG-LICENSE.txt` |

RAxML-NG is AGPL-3.0: every release attaches
`raxml-ng-2.0.3-source+patch.tar.gz` with the exact sources and the patch
used for the Windows build. Versions and download URLs are listed in
`packaging/third_party.json`.
