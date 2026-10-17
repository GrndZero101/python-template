#!/bin/sh
# Make sure of a uv this template can trust, then hand off to bootstrap.py beside this file.
#
#   sh bootstrap.sh doctor          # from a clone of this repo
#   sh bootstrap.sh --yes doctor    # consent in advance, where there is no terminal to ask at
#
# A uv it can trust is one at or above UV_VERSION, installed by the standalone installer so that
# `uv self update` works. There is no way around that check: everything after it, in bootstrap.py,
# relies on it. Everything else is bootstrap.py's job; this file stays as thin as it can.
#
# POSIX sh only. /bin/sh is dash on Ubuntu and bash in POSIX mode on macOS, so no pipefail, no
# [[ ]], no `local` and no arrays. No output of uv's is parsed: its exit codes and
# `uv self version --short` are the whole interface.
#
# Exits 1 when uv cannot be used, having said why and what to do; otherwise bootstrap.py's code.

set -eu

# The uv floor. tests/test_bootstrap_sh.py holds every other copy to this line: `required-version`
# in the pyprojects, and setup-uv's `version` in CI.
UV_VERSION=0.12.21

say() {
    printf 'bootstrap: %s\n' "$*" >&2
}

fail() {
    say "$@"
    exit 1
}

# Succeed when version $1 is older than $2, field by dot-separated field. awk, because `sort -V`
# is not POSIX.
older_than() {
    awk -v have="$1" -v want="$2" 'BEGIN {
        split(have, h, ".")
        split(want, w, ".")
        for (i = 1; i <= 3; i++) {
            if (h[i] + 0 < w[i] + 0) exit 0
            if (h[i] + 0 > w[i] + 0) exit 1
        }
        exit 1
    }'
}

# Succeed when the user agrees to $1: --yes, or a "y" typed at a terminal. With neither, stop.
consent() {
    if [ "$assume_yes" = 1 ]; then
        return 0
    fi
    if [ ! -t 0 ]; then
        fail "$1 needs consent, and there is no terminal to ask at; rerun as: sh bootstrap.sh --yes ..."
    fi
    printf 'bootstrap: %s? [y/N] ' "$1" >&2
    read -r answer || answer=
    case $answer in
        y | Y | yes) return 0 ;;
        *) return 1 ;;
    esac
}

# Write the body of URL $1 to stdout.
fetch() {
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$1"
    else
        fail "neither curl nor wget is installed; install one, then rerun"
    fi
}

# Install uv at the pin and point $uv at it. PATH in this process has not changed, so the new uv
# is used by absolute path for the rest of the run.
install_uv() {
    consent "uv is not on PATH. Install uv $UV_VERSION with the official installer" ||
        fail "uv is required: rerun and agree, or install it from https://docs.astral.sh/uv/"
    # Into a variable first, so a failed download stops here instead of piping nothing to sh.
    installer=$(fetch "https://astral.sh/uv/$UV_VERSION/install.sh")
    # stdout is bootstrap.py's, for its report; the installer's progress is diagnostics.
    printf '%s\n' "$installer" | sh >&2
    uv="${UV_INSTALL_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}/uv"
    if [ ! -x "$uv" ]; then
        fail "the installer finished, but there is no uv at $uv; set UV_INSTALL_DIR to where it went"
    fi
}

not_standalone() {
    fail "this uv cannot update itself (the error is above). Either it was installed by Homebrew," \
        "pip or a package manager, or another copy shadows the standalone one (\`which -a uv\`):" \
        "remove that copy (\`brew uninstall uv\`, \`pip uninstall uv\`) and rerun, which installs" \
        "the standalone uv. Or the check could not reach GitHub: rerun when online."
}

assume_yes=0
if [ "${1-}" = --yes ]; then
    assume_yes=1 # and still passed on: bootstrap.py takes --yes too
fi

if ! uv=$(command -v uv); then
    install_uv
fi

# A uv too old to have `self version` reads as 0, so it takes the update path below.
if ! have=$("$uv" self version --short 2>/dev/null); then
    have=0
fi

if older_than "$have" "$UV_VERSION"; then
    consent "uv $have is older than $UV_VERSION, this template's floor. Update it" ||
        fail "uv $UV_VERSION or newer is required: rerun and agree, or run: uv self update $UV_VERSION"
    "$uv" self update "$UV_VERSION" || not_standalone
elif ! check=$("$uv" self update --dry-run 2>&1); then
    printf '%s\n' "$check" >&2
    not_standalone
fi

here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ ! -f "$here/bootstrap.py" ]; then
    fail "no bootstrap.py beside this script: run it from a clone, as sh bootstrap.sh"
fi
# uv's own directory first, so bootstrap.py finds the uv just installed or vetted, and the uv
# tools beside it, before anything else on PATH.
PATH="$(dirname -- "$uv"):$PATH"
export PATH
exec "$uv" run --script "$here/bootstrap.py" "$@"
