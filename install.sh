#!/usr/bin/env bash
# Small bootstrap: prompts always use the terminal, including curl | bash.
set -Eeuo pipefail
repo_url='https://github.com/mohammadrezafathi92-web/shared-agent-memory.git'
trap 'printf "\nInstallation stopped. Existing data was not removed. / نصب متوقف شد؛ داده‌ها حذف نشدند.\n" >&2' ERR
if ! (: </dev/tty) 2>/dev/null; then
  echo 'An interactive terminal is required. For automation use scripts/install.py --config FILE.' >&2
  exit 1
fi
ask() { printf '%s' "$1" >/dev/tty; IFS= read -r reply </dev/tty; }
missing=()
for dependency in git python3; do
  command -v "$dependency" >/dev/null 2>&1 || missing+=("$dependency")
done
if ((${#missing[@]})); then
  [[ -f /etc/os-release ]] && . /etc/os-release
  if [[ "${ID:-}" != ubuntu ]]; then
    echo 'Install git and Python 3 first; automatic prerequisite installation supports Ubuntu.' >&2
    exit 1
  fi
  ask 'Install git/Python prerequisites with apt? / نصب پیش‌نیازها؟ [y/N] '
  [[ "$reply" == y || "$reply" == Y ]] || exit 1
  privilege=()
  if ((EUID != 0)); then privilege=(sudo); fi
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y git python3 ca-certificates
fi
local_root=''
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  candidate=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  if [[ -f "$candidate/scripts/install.py" && -f "$candidate/compose.yaml" ]]; then
    local_root=$candidate
  fi
fi
if [[ -n "$local_root" ]]; then
  target=$local_root
else
  ask "Install directory / مسیر نصب [$HOME/shared-agent-memory]: "
  target=${reply:-"$HOME/shared-agent-memory"}
  case "$target" in '~/'*) target="$HOME/${target:2}";; esac
  if [[ -d "$target/.git" ]]; then
    remote=$(git -C "$target" remote get-url origin)
    if [[ "$remote" != "$repo_url" && "$remote" != "${repo_url%.git}" ]]; then
      echo 'This directory belongs to a different repository; choose an empty directory.' >&2
      exit 1
    fi
    echo 'Resuming the installed checkout; no automatic git reset or upgrade.'
  else
    git clone --depth 1 -- "$repo_url" "$target"
  fi
fi
exec python3 "$target/scripts/install.py" </dev/tty
