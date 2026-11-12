# English and German menu builds

The Stage 2 menu supports English (`en`, default) and German (`de`). Both
variants use the same C/assembly code, disk layout, keys and validation rules.
Language selection changes the menu text, not the boot logic. The early boot
messages, failure codes and automated-test markers remain English ASCII.

## Building and alternating languages

After `make toolchain`, with the prerequisites listed in the root README:

```sh
make hdd RB_LANGUAGE=en
make hdd RB_LANGUAGE=de
make hdd RB_LANGUAGE=en
```

Each invocation performs a complete native build. English and German have
separate fixed output directories; switching language does not reuse an
object or generated header from the other build. No clean step is required.
The language cannot currently be changed inside the running menu.

| Purpose | English | German |
| --- | --- | --- |
| Compact image | `build/hdd/retroboot-hdd.img` | `build/hdd-de/retroboot-hdd.img` |
| T07 handoff-test image | `build/hdd/retroboot-handoff.img` | `build/hdd-de/retroboot-handoff.img` |
| Independent repeat build | `build/hdd-repeat/` | `build/hdd-repeat-de/` |
| General menu evidence | `build/menu/` | `build/menu-de/` |
| Scanner and paging evidence | `build/scan/` | `build/scan-de/` |
| Volume header evidence | `build/volume/` | `build/volume-de/` |
| Configuration evidence | `build/config/` | `build/config-de/` |
| Handoff evidence | `build/handoff/` | `build/handoff-de/` |

The **retroboot-hdd-bios** CI artifact contains both compact diagnostic images
and both separate 128 MiB handoff-test images. Inside
the archive the paths start with `hdd/` and `hdd-de/`; the outer `build/`
directory is omitted. A new image needs a fresh raw-to-VDI conversion for
VirtualBox; an older VDI still contains the older program.

## Characters and encoding

The source catalogs [en.json](../ui/en.json) and [de.json](../ui/de.json) are
UTF-8. The build converts the selected catalog to CP437 for the BIOS VGA text
mode and writes an ASCII C header using exactly three octal digits per byte.
This avoids dependence on the host or compiler locale and prevents a following
digit from extending an escape sequence.

| Character | CP437 byte, hexadecimal |
| --- | --- |
| Ä | `8E` |
| Ö | `99` |
| Ü | `9A` |
| ä | `84` |
| ö | `94` |
| ü | `81` |
| ß (Eszett) | `E1` |

The mapping is recorded in the [Unicode Consortium's CP437 table](https://www.unicode.org/Public/MAPPINGS/VENDORS/MICSFT/PC/CP437.TXT).
For example, German screens contain `Köpfe`, `Menü`, `Überlappende` and
`außerhalb`. The original `ae/oe/ue` spellings were text choices, not a limit
of VGA output. Writing unconverted UTF-8 bytes into VGA text memory would
produce incorrect characters.

The build rejects missing or duplicate keys, extra keys, empty text, control
characters, characters outside CP437 and text exceeding its assigned screen
field. CP437 is not full Unicode: the capital `ẞ` and the euro sign, for
example, are not representable. Rendering assumes a VGA-compatible CP437
font supplied by the BIOS. No custom font is installed.

## Verification

```sh
make check
make hdd-test RB_LANGUAGE=en
make hdd-ui-test RB_LANGUAGE=de
```

The 126 host tests include seven catalog tests, with independent byte values
for all six umlauts and `ß`, field bounds and stale-language detection.
Each language is built twice and all binaries, images and manifests must
match between its two builds. Different languages are expected to produce
different Stage 2 binaries.

The full 100-case boot suite runs once in CI with English, covering the shared
loader, C startup, native menu-model, parser, arithmetic, configuration and handoff preparation tests. Both languages
run all five general menu campaigns, 32 scanner, 43 volume-header and 43
handoff, 63 configuration, 65 installation-state, 37 visibility and
37 checked-profile and 37 allocation-audit campaigns: 3,186 VGA/keyboard states per language, 6,372 total. Every visible
translated label, including scanner and header errors, is checked against the selected
catalog. Image hashes, RAM/BSS/stack checks and disk-write monitoring remain
active. QEMU screenshots provide additional visual evidence.

The build manifest records the selected language, `cp437` encoding and the
catalog SHA-256. UI tests reject a stale or mismatched catalog and require
the matching `RB UI en CP437` or `RB UI de CP437` boot marker. Test reports
include the same metadata. A full German boot suite is also available with
`make hdd-test RB_LANGUAGE=de`; it is not duplicated in CI because the shared
boot logic is unchanged.

Manual success for both language variants from PR #8 was reported on
10 November 2026. No new platform details were supplied; a particular
historical VGA/BIOS configuration is therefore not established. F3 from PR #9
and the [T07 handoff image](Handoff.md) from PR #10 were subsequently confirmed
too, without further platform details. The F5 test from merged PR #11 was reported complete without added coverage details.
F6 was subsequently confirmed. German F7 screenshots were confirmed under
VirtualBox on 12 November 2026. English F7 followed by the
[F9 checked-profile path](ProfileTest.md) was confirmed there on
13 November 2026, including `RB HANDOFF PASS`. The new [F10 manual check](AdminAllocation.md)
remains pending. T07 target-side PASS/FAIL remains English ASCII.
