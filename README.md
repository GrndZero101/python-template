# python-template

A [copier](https://copier.readthedocs.io/) template for Python projects built around one idea:
every rule in the generated `CLAUDE.md` exists so a human (or an AI agent) can stop the program and
inspect it. Structure, debuggability and portability rules are mechanically enforced by lint config
and a `prek` gate — not just documented and hoped for.

## Layout

- **`template/`** — everything a generated project receives. It is an ordinary, runnable Python
  project: it has its own tests, its own gate, and is held to the rules it ships.
- **`.pre-commit-config.yaml`** — the gate for this repository. It owns the commit-level rules and
  delegates all code checking into `template/`, so the lint list exists in exactly one place.
- **`CLAUDE.md`** — how to work on the template. Imports `template/CLAUDE.md` for the rules
  themselves.
- **`TODO.md`** — outstanding work.

## Status

Mid-conversion. The tree has been restructured for `_subdirectory`, but `copier.yml` does not exist
yet and the package name, project type and example code are still fixed to the `geo`/`currency`
demo. See [TODO.md](TODO.md).

## Working on it

```bash
prek install && prek install -t commit-msg && prek install -t pre-merge-commit
prek run --all-files                  # delegates into template/
uv run --directory template pytest    # the generated project's own suite
```

All three shims are required — `prek install` alone wires only `pre-commit`, which silently skips
the commit-message check and breaks `--no-ff` merges into `main`.

## License

[MIT](LICENSE)
