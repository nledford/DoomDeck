#!/usr/bin/env sh
set -eu

# Install DoomDeck from a GitHub source archive without requiring PyPI.
#
# Typical use:
#   curl -LsSf https://raw.githubusercontent.com/nledford/DoomDeck/master/install.sh | sh
#
# Optional environment variables:
#   DOOMDECK_REPO_URL      GitHub repo URL. Default: https://github.com/nledford/DoomDeck
#   DOOMDECK_REF           Branch name. Default: master
#   DOOMDECK_ARCHIVE_URL   Full source archive URL. Overrides DOOMDECK_REPO_URL/DOOMDECK_REF.
#   DOOMDECK_INSTALL_DIR   Source install directory. Default: $HOME/.local/share/doomdeck/source
#   DOOMDECK_BIN_DIR       Wrapper install directory. Default: $HOME/.local/bin
#   DOOMDECK_COMMAND       Wrapper command name. Default: doomdeck
#   PYTHON                 Python executable. Default: python3

info() {
    printf '%s\n' "doomdeck: $*"
}

fail() {
    printf '%s\n' "doomdeck: error: $*" >&2
    exit 1
}

repo_url=${DOOMDECK_REPO_URL:-https://github.com/nledford/DoomDeck}
ref=${DOOMDECK_REF:-master}
archive_url=${DOOMDECK_ARCHIVE_URL:-"$repo_url/archive/refs/heads/$ref.tar.gz"}
install_dir=${DOOMDECK_INSTALL_DIR:-"$HOME/.local/share/doomdeck/source"}
bin_dir=${DOOMDECK_BIN_DIR:-"$HOME/.local/bin"}
command_name=${DOOMDECK_COMMAND:-doomdeck}
python_cmd=${PYTHON:-python3}

case "$command_name" in
    "" | */*) fail "DOOMDECK_COMMAND must be a command name, not a path" ;;
esac

[ -n "$install_dir" ] || fail "DOOMDECK_INSTALL_DIR must not be empty"
[ -n "$bin_dir" ] || fail "DOOMDECK_BIN_DIR must not be empty"

command -v tar >/dev/null 2>&1 || fail "tar is required"
python_path=$(command -v "$python_cmd") || fail "$python_cmd is required"

"$python_path" - <<'PY' || fail "Python 3.10 or newer is required"
import sys

raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY

tmp_root=$(mktemp -d "${TMPDIR:-/tmp}/doomdeck-install.XXXXXX") || fail "could not create a temporary directory"
cleanup() {
    rm -rf "$tmp_root"
}
trap cleanup EXIT HUP INT TERM

download_archive() {
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf "$archive_url" -o "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$1" "$archive_url"
    else
        fail "curl or wget is required"
    fi
}

archive_path="$tmp_root/doomdeck.tar.gz"
extract_dir="$tmp_root/extract"
tmp_install="$tmp_root/source"
launcher="$bin_dir/$command_name"
previous_install="$install_dir.previous"

info "Downloading $archive_url"
download_archive "$archive_path" || fail "failed to download DoomDeck source archive"

mkdir -p "$extract_dir" "$tmp_install"
tar -xzf "$archive_path" -C "$extract_dir" || fail "failed to extract DoomDeck source archive"

source_dir=$(find "$extract_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)
[ -n "$source_dir" ] || fail "source archive did not contain a top-level directory"
[ -f "$source_dir/pyproject.toml" ] || fail "source archive is missing pyproject.toml"
[ -d "$source_dir/src/doomdeck" ] || fail "source archive is missing src/doomdeck"

(
    cd "$source_dir"
    tar -cf - .
) | (
    cd "$tmp_install"
    tar -xf -
)

PYTHONPATH="$tmp_install/src" "$python_path" -m doomdeck --help >/dev/null ||
    fail "downloaded DoomDeck source failed its import smoke test"

mkdir -p "$(dirname "$install_dir")" "$bin_dir"

if [ -e "$previous_install" ]; then
    rm -rf "$previous_install"
fi

if [ -e "$install_dir" ]; then
    mv "$install_dir" "$previous_install"
fi

if ! mv "$tmp_install" "$install_dir"; then
    if [ -e "$previous_install" ]; then
        mv "$previous_install" "$install_dir"
    fi
    fail "failed to install DoomDeck into $install_dir"
fi

"$python_path" - "$launcher" "$install_dir" "$python_path" <<'PY'
import os
import sys
from pathlib import Path

launcher, install_dir, python_path = sys.argv[1:]
content = f"""#!/usr/bin/env sh
set -eu
DOOMDECK_INSTALL_DIR={install_dir!r}
PYTHON={python_path!r}
export PYTHONPATH="$DOOMDECK_INSTALL_DIR/src${{PYTHONPATH:+:$PYTHONPATH}}"
exec "$PYTHON" -m doomdeck "$@"
"""
Path(launcher).write_text(content, encoding="utf-8")
os.chmod(launcher, 0o755)
PY

"$launcher" --help >/dev/null || fail "installed doomdeck command failed its smoke test"

if [ -e "$previous_install" ]; then
    rm -rf "$previous_install"
fi

info "Installed DoomDeck source to $install_dir"
info "Installed command wrapper to $launcher"

case ":$PATH:" in
    *":$bin_dir:"*) info "Run: $command_name install" ;;
    *)
        info "$bin_dir is not on PATH in this shell"
        info "Run now with: $launcher install"
        info "Or add this to your shell profile: export PATH=\"$bin_dir:\$PATH\""
        ;;
esac
