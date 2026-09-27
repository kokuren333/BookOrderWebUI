# Third-party runtime redistribution

This job is an aggregate of independent command-line programs. Their own
licenses apply separately; do not impose restrictions that take away their
recipients' rights. The runtime tools are not authored by this project.

- Pandoc 3.11: GPL version 2 or later. Original COPYRIGHT and GPL text are
  included. `sources/` contains the matching Pandoc repository with its build
  scripts, Haskell dependency source archives inventoried from the distributed
  executables' embedded GHC unit IDs, GHC sources including runtime libraries,
  and native zlib/GMP sources. `pandoc-linked-units.json` and
  `source-manifest.json` describe the inventory and SHA-256 hashes. Long GHC
  package names may be abbreviated: all matching version candidates are kept.
  Source archives include their own notices. No written source offer or remote
  download is needed: keep these source archives with every redistributed job
  and result ZIP. Tools are unmodified upstream executables.
- Windows Python: official CPython 3.14.7 embeddable distribution, retaining
  its complete LICENSE.txt and native dependencies. Bootstrap adjusts only
  the documented ._pth configuration so job scripts can import each other.
- macOS/Linux Python: Astral python-build-standalone CPython 3.12.14,
  release 20260924. Original runtime and vendor notices are retained. Matching
  CPython, Berkeley DB source and standalone build scripts are included for
  the Berkeley DB/Sleepycat source-access condition. The build project is MPL
  2.0; its source is included unmodified. Python and its libraries each retain
  their own license; consult the full `python-licenses.rst` and archived files.
- Typst CLI 0.15.1: Apache License 2.0. LICENSE and NOTICE, including upstream
  third-party attribution, are retained unmodified. The matching Typst source
  and every registry crate in its Cargo.lock are included with original notices
  and checksums, including embedded font assets and native-library sources.
- Noto Serif CJK JP Regular/Bold: SIL Open Font License 1.1. Binaries are
  unmodified. Attribution and license are retained; fonts are bundled as part
  of the software, not sold on their own. The font license does not require
  created publications to use OFL.

- Noto Sans JP (Regular/Bold, Noto CJK Sans 2.004 release), Source Serif 4
  (4.005R), Inter (4.1) and JetBrains Mono (2.304): SIL Open Font License 1.1.
  Unmodified binaries extracted from the pinned upstream release archives
  (SHA-256 verified); each family's licence is kept in
  third-party/licenses/<family>/. The static website copies the used Latin
  families together with their licence. Fonts are bundled with the software,
  not sold on their own, and the OFL does not apply to created publications.

Upstream references:
https://github.com/jgm/pandoc/tree/3.11
https://www.python.org/downloads/release/python-3147/
https://github.com/astral-sh/python-build-standalone/tree/20260924
https://github.com/typst/typst/tree/v0.15.1
https://github.com/notofonts/noto-cjk
https://github.com/adobe-fonts/source-serif
https://github.com/rsms/inter
https://github.com/JetBrains/JetBrainsMono

`runtime/manifest.json` records the exact original binary URLs and checksums.
`source-manifest.json` records locally supplied source archives. The static
host must deploy every catalogue part together; the generator refuses missing
or corrupt parts rather than emitting an incomplete runtime job.
