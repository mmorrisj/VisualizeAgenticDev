#!/usr/bin/env bash
# Create a fresh, git-tracked copy of practice-app for an exercise.
# Usage: ./setup.sh [target-dir]   (default: ~/practice-app)
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/template"
TARGET="${1:-$HOME/practice-app}"

if [[ -e "$TARGET" ]]; then
  echo "Refusing to overwrite existing path: $TARGET" >&2
  echo "Remove it or pass a different target directory." >&2
  exit 1
fi

cp -r "$SRC_DIR" "$TARGET"
mv "$TARGET/dot-env" "$TARGET/.env"
mv "$TARGET/dot-gitignore" "$TARGET/.gitignore"

cd "$TARGET"
git init -q
git symbolic-ref HEAD refs/heads/main   # same branch name on every git version
git add .
git -c user.name="trainee" -c user.email="trainee@localhost" commit -q -m "Starting point"

echo "practice-app ready at: $TARGET"
echo "Clean baseline committed. Undo any changes with: git checkout . && git clean -fd"
