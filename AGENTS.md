# Repository conventions

- Repository documentation uses neutral, impersonal language. Avoid direct
  conversational address in any language, including German personal pronouns
  and English second-person wording.
- Do not include the repository owner's real name or private personal details
  in files, examples, commit messages, or pull-request descriptions. Use project
  names or roles; GitHub handles are sufficient where an identifier is needed.
- Record manual test results as technical evidence. Do not invent a machine,
  BIOS version, or test environment when the report does not specify one.
- Keep menu text in the UTF-8 catalogs under `ui/`. The build selects one
  language and emits CP437 bytes for VGA; runtime logic is shared.
- Boot failure codes and automated-test markers remain stable English ASCII.
- The specification's technical contracts remain authoritative. Mark editorial
  changes to archived conversation material; do not silently revise its old
  technical claims into current requirements.
