#!/usr/bin/env sh
set -eu

# Install DoomDeck from a GitHub source archive.
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
archive_url=${DOOMDECK_ARCHIVE_URL:-}
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

if [ -z "$archive_url" ]; then
    resolved_ref=$(
        "$python_path" - "$repo_url" "$ref" <<'PY'
import json
import re
import sys
import urllib.parse
import urllib.request

repo_url, ref = sys.argv[1:]
normalized = repo_url.rstrip("/")
if normalized.endswith(".git"):
    normalized = normalized[:-4]
parsed = urllib.parse.urlparse(normalized)
parts = [part for part in parsed.path.split("/") if part]
if parsed.scheme != "https" or (parsed.hostname or "").lower() != "github.com" or len(parts) != 2:
    raise SystemExit("DOOMDECK_REPO_URL must be an https://github.com/OWNER/REPO URL")
api_url = f"https://api.github.com/repos/{parts[0]}/{parts[1]}/commits/{urllib.parse.quote(ref, safe='')}"
request = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": "doomdeck-installer"})


def validate_url(target):
    parsed_target = urllib.parse.urlparse(target)
    if parsed_target.scheme != "https" or (parsed_target.hostname or "").lower() != "api.github.com":
        raise ValueError(f"GitHub metadata redirect is not allowed: {target}")


class ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


validate_url(api_url)
opener = urllib.request.build_opener(ValidatingRedirectHandler())
with opener.open(request, timeout=30) as response:
    validate_url(response.geturl())
    sha = json.load(response).get("sha", "")
if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
    raise SystemExit(f"GitHub did not return a commit SHA for {ref}")
print(sha)
PY
    ) || fail "failed to resolve DoomDeck ref $ref to an immutable GitHub commit"
    normalized_repo_url=${repo_url%/}
    normalized_repo_url=${normalized_repo_url%.git}
    archive_url="$normalized_repo_url/archive/${resolved_ref}.tar.gz"
fi

tmp_root=$(mktemp -d "${TMPDIR:-/tmp}/doomdeck-install.XXXXXX") || fail "could not create a temporary directory"
cleanup() {
    rm -rf "$tmp_root"
}
trap cleanup EXIT HUP INT TERM

download_archive() {
    "$python_path" - "$archive_url" "$1" "${DOOMDECK_ARCHIVE_URL:+explicit}" <<'PY'
import shutil
import sys
import urllib.parse
import urllib.request

url, destination, explicit = sys.argv[1:]


def validate_url(target):
    parsed = urllib.parse.urlparse(target)
    if explicit and parsed.scheme == "file":
        return
    if parsed.scheme != "https":
        raise ValueError(f"source archive URL must use https: {target}")
    hostname = (parsed.hostname or "").lower()
    if not explicit and hostname != "github.com" and not hostname.endswith(".github.com"):
        raise ValueError(f"source archive redirect host is not allowed: {hostname or '<missing>'}")


class ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


validate_url(url)
opener = urllib.request.build_opener(ValidatingRedirectHandler())
request = urllib.request.Request(url, headers={"User-Agent": "doomdeck-installer"})
with opener.open(request, timeout=60) as response, open(destination, "wb") as output:
    validate_url(response.geturl())
    shutil.copyfileobj(response, output)
PY
}

archive_path="$tmp_root/doomdeck.tar.gz"
extract_dir="$tmp_root/extract"
tmp_install="$tmp_root/source"
launcher="$bin_dir/$command_name"
previous_install="$install_dir.previous"
requirements_path="$tmp_install/requirements-runtime.lock"

info "Downloading $archive_url"
download_archive "$archive_path" || fail "failed to download DoomDeck source archive"

mkdir -p "$extract_dir" "$tmp_install"
"$python_path" - "$archive_path" "$extract_dir" <<'PY' || fail "failed to safely extract DoomDeck source archive"
import os
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive_path = Path(sys.argv[1])
dest = Path(sys.argv[2]).resolve()


def reject(message):
    print(f"unsafe source archive: {message}", file=sys.stderr)
    raise SystemExit(1)


try:
    with tarfile.open(archive_path, "r:gz") as archive:
        validated = []
        for member in archive.getmembers():
            member_path = PurePosixPath(member.name)
            parts = member_path.parts
            if member_path.is_absolute():
                reject(f"absolute path: {member.name}")
            if not parts or any(part in {"", ".", ".."} for part in parts):
                reject(f"unsafe path: {member.name}")
            target = dest.joinpath(*parts).resolve()
            try:
                target.relative_to(dest)
            except ValueError:
                reject(f"path escapes extraction directory: {member.name}")
            if member.issym() or member.islnk():
                reject(f"link member: {member.name}")
            if not member.isfile() and not member.isdir():
                reject(f"special file: {member.name}")
            validated.append((member, target))

        for member, target in validated:
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                reject(f"unreadable file member: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            os.chmod(target, member.mode & 0o755)
except tarfile.TarError as exc:
    print(f"invalid source archive: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY

source_dir=$(find "$extract_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)
[ -n "$source_dir" ] || fail "source archive did not contain a top-level directory"
[ -f "$source_dir/pyproject.toml" ] || fail "source archive is missing pyproject.toml"
[ -f "$source_dir/requirements-runtime.lock" ] || fail "source archive is missing requirements-runtime.lock"
[ -d "$source_dir/src/doomdeck" ] || fail "source archive is missing src/doomdeck"

(
    cd "$source_dir"
    tar -cf - .
) | (
    cd "$tmp_install"
    tar -xf -
)

venv_dir="$tmp_install/.venv"
"$python_path" -m venv "$venv_dir" || fail "failed to create DoomDeck Python environment"
venv_python="$venv_dir/bin/python"
[ -x "$venv_python" ] || fail "DoomDeck Python environment is missing its interpreter: $venv_python"

"$venv_python" -m pip install --disable-pip-version-check --require-hashes --requirement "$requirements_path" ||
    fail "failed to install DoomDeck Python dependencies"

PYTHONPATH="$tmp_install/src" "$venv_python" -m doomdeck --help >/dev/null ||
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

"$python_path" - "$launcher" "$install_dir" <<'PY'
import os
import sys
from pathlib import Path

launcher, install_dir = sys.argv[1:]
content = f"""#!/usr/bin/env sh
set -eu
DOOMDECK_INSTALL_DIR={install_dir!r}
DOOMDECK_PYTHON="$DOOMDECK_INSTALL_DIR/.venv/bin/python"
if [ ! -x "$DOOMDECK_PYTHON" ]; then
    printf '%s\\n' "doomdeck: error: missing DoomDeck Python environment: $DOOMDECK_PYTHON" >&2
    exit 1
fi
export PYTHONPATH="$DOOMDECK_INSTALL_DIR/src${{PYTHONPATH:+:$PYTHONPATH}}"
exec "$DOOMDECK_PYTHON" -m doomdeck "$@"
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
