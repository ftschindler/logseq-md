# Contributing

## System requirements

Everything runs through [uv](https://docs.astral.sh/uv/), which is the only thing you have to
install yourself.

| Tool | Why | Install |
| --- | --- | --- |
| `uv` / `uvx` | runs the package, the tests and every hook | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| `git` | the guard suite asks git what would be committed | your package manager |
| `node` | the link checker drives a headless browser | [nodejs.org](https://nodejs.org/) |
| `make` | a convenience, not a dependency; every target is one line | optional, and usually absent on Windows |

## The loop

```sh
make bootstrap   # once per clone: installs the pre-commit hooks
make test        # the suite
make check       # every hook over every file, which is what CI runs
```

`make check` and CI run the same command, so a green local run is a green pull request.

## House rules worth knowing before the hooks tell you

- **Markdown carries no thematic breaks and no em dashes.** Headings already separate sections,
  and `-` is typeable on every keyboard and greps the same everywhere.
- **Filenames are lowercase with no whitespace**, with a short allowlist for the files whose
  uppercase names are conventions other tools look for.
- **No symlinks.** A Windows clone without developer mode turns one into a text file holding a
  path, and every reader downstream gets that string as the document.
- **Invoke the command as `uvx logseq-md`.** The distribution and the command share a name, so
  the longer spelling is noise, and a guard keeps it out of the documentation.
- **The version in `pyproject.toml` belongs to the release job.** A pull request that edits it is
  refused. What a pull request carries instead is a label saying how big it is: `major`, `minor`,
  `patch` or `no-release`.

## Pull requests

One bump label, exactly. Two is a disagreement rather than a bigger bump.
