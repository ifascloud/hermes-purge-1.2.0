#!/usr/bin/env bash
set -euo pipefail

VERSION="1.2.0"
PLUGIN_NAME="hermes-purge"
PACKAGE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${HERMES_HOME:-}" ]]; then
  HERMES_HOME="$HERMES_HOME"
elif [[ -n "${LOCALAPPDATA:-}" ]] && command -v cygpath >/dev/null 2>&1; then
  HERMES_HOME="$(cygpath -u "$LOCALAPPDATA")/hermes"
else
  HERMES_HOME="$HOME/.hermes"
fi
DEST="$HERMES_HOME/src/${PLUGIN_NAME}-export-${VERSION}"

for command in hermes git; do
  command -v "$command" >/dev/null 2>&1 || { printf 'Missing required command: %s\n' "$command" >&2; exit 1; }
done

hermes plugins validate "$PACKAGE_DIR"
if [[ -e "$DEST" ]]; then
  printf 'Refusing to overwrite existing source directory: %s\n' "$DEST" >&2
  exit 1
fi

mkdir -p "$(dirname -- "$DEST")"
if [[ -e "$HERMES_HOME/plugins/$PLUGIN_NAME" ]]; then
  printf 'Plugin already exists at %s; refusing to replace it.\n' "$HERMES_HOME/plugins/$PLUGIN_NAME" >&2
  exit 1
fi
cp -R "$PACKAGE_DIR" "$DEST"
rm -rf "$DEST/.git"
git -C "$DEST" init -q
git -C "$DEST" add -A
git -C "$DEST" -c user.name=hermes-purge -c user.email=hermes-purge@localhost commit -qm "Export hermes-purge ${VERSION}"

PLUGIN_URL="file://$(cygpath -m "$DEST" 2>/dev/null || printf '%s' "$DEST")"
hermes plugins install "$PLUGIN_URL" --enable
hermes plugins doctor "$DEST" --ci
printf 'Installed source: %s\n' "$DEST"
printf 'Start a new chat session before checking the injected prompt section.\n'
