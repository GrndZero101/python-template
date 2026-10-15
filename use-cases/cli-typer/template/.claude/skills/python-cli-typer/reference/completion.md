# Shell completion — do not ship `--install-completion`

Why the scaffold sets `add_completion=False`, and how users get completion instead.

Typer's installer is destructive and wrong under a custom `$ZDOTDIR`
(`typer/_completion_shared.py`, verified in 0.27.0):

- `zshrc_path = Path.home() / ".zshrc"` — **`$ZDOTDIR` is never consulted**, so with a custom
  location it writes to a file zsh never reads.
- It **rewrites your `.zshrc`** with `write_text` and no backup.
- It appends an unconditional `fpath+=~/.zfunc; autoload -Uz compinit; compinit`, which double-runs
  `compinit` if you already use oh-my-zsh, zinit or a compiled zcompdump.
- It gates its `zstyle` injection on a naive `"zstyle" not in content` check over the whole file.

So disable it and emit the script to stdout instead, letting the user or the package manager place
it:

```python
app = typer.Typer(add_completion=False)
```

```bash
# note: source_zsh, NOT zsh_source — typer inverts Click 8's order for back-compat
_TOOL_COMPLETE=source_zsh tool > "${ZDOTDIR:-$HOME}/completions/_tool"
```

That output is a clean `#compdef` block with no `fpath` or `compinit` lines. The env var is derived
from the program name, uppercased — so a `prog_name` containing a dot yields an invalid variable;
rely on the `[project.scripts]` name. `source_bash`, `source_fish` and `source_powershell` work the
same way.

Document this in the README. `--show-completion` is not a substitute: it uses shellingham to detect
the *parent process*, so it cannot cross-generate another shell's script.
