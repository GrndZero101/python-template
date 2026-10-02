# Interactive prompts

Read before asking the user anything mid-command.

`prompt_toolkit` (optionally `questionary` on top of it) for confirm, select and autocomplete inside
a normal command. Full-screen applications are **python-tui**.

A prompt in a non-interactive context is a **hang**, not an error, so guard every one:

- Prompt only when `sys.stdin.isatty() and sys.stderr.isatty()`.
- **Never prompt when `-o json`** — a machine consumer cannot answer.
- `--yes` to assume confirmation; `--no-input` to fail rather than ask.
- With no tty and no `--yes`, exit **2** with a message naming the flag that would have avoided it:
  `"refusing to prompt without a terminal; pass --yes to confirm"`.
- **Route the prompt to stderr.** `prompt_toolkit` writes to stdout by default, which corrupts the
  data stream: `create_output(stdout=sys.stderr)`.

Keep the answer collection separate from the action, so the action stays callable with literal
arguments and the tests never prompt.
