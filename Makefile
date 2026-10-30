.DEFAULT_GOAL := help

## Show available targets
help:
	@grep -B1 '^[a-z][a-z_-]*:' $(MAKEFILE_LIST) \
		| grep -A1 '^##' \
		| awk '/^##/{d=substr($$0,4)} /^[a-z]/{split($$0,a,":"); printf "  %-20s %s\n", a[1], d}'

# Fail early with an actionable message when a required tool is missing, rather
# than letting a recipe die halfway with a cryptic "command not found". Each
# target lists the binaries it assumes as `guard-<tool>` order-only prereqs.
guard-%:
	@command -v $* >/dev/null 2>&1 || { \
		printf 'error: required tool %s not found on PATH.\n' '$*' >&2; \
		printf 'See CONTRIBUTING.md > System requirements for how to install it.\n' >&2; \
		exit 1; \
	}

## Run the test suite
test: | guard-uv
	uv run --group dev pytest

## Run the suite against a real graph named by LOGSEQ_MD_TEST_GRAPH (local only)
# Never in CI, and never with anything from that graph copied in here. A
# personal graph is the only corpus ugly enough to find the real bugs, and the
# only one that must not be published.
test_graph: | guard-uv
	uv run --group dev pytest -m graph

## Build the wheel and the sdist into dist/
build: | guard-uv
	uv build --out-dir dist

## Run the full pre-commit guard suite against all files
check: | guard-uvx
	uvx prek run --all-files

## Install the pre-commit hooks into this clone
bootstrap: | guard-git guard-uvx
	uvx prek install

.PHONY: help test test_graph build check bootstrap
