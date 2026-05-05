#!/usr/bin/env bash
# Download the Chinook SQLite database into the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."

URL="https://github.com/lerocha/chinook-database/raw/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite"
DEST="chinook.db"

if [ -f "$DEST" ]; then
  echo "$DEST already exists. Skipping download."
  exit 0
fi

echo "Downloading Chinook database to $DEST..."
curl -L -o "$DEST" "$URL"
echo "Done. Size: $(du -h "$DEST" | cut -f1)"
