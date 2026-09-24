#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

DIST_NAME="plat-reader-standalone"
TAR_FILE="${DIST_NAME}.tar.gz"
ZIP_FILE="${DIST_NAME}.zip"

echo "Packaging ${DIST_NAME}..."

# Exclude temporary cache directories and upload artifacts
EXCLUDES=(
    --exclude='plat-reader/**/__pycache__'
    --exclude='plat-reader/**/*.pyc'
    --exclude='plat-reader/**/.pytest_cache'
    --exclude='plat-reader/**/.ruff_cache'
    --exclude='plat-reader/backend/uploads/*'
    --exclude='plat-reader/backend/output/*'
)

tar -czf "$TAR_FILE" "${EXCLUDES[@]}" plat-reader/
echo "Created: $TAR_FILE ($(du -h "$TAR_FILE" | cut -f1))"

if command -v zip >/dev/null 2>&1; then
    zip -q -r "$ZIP_FILE" plat-reader/ -x "*/__pycache__/*" "*.pyc" "*/.pytest_cache/*" "*/backend/uploads/*" "*/backend/output/*"
    echo "Created: $ZIP_FILE ($(du -h "$ZIP_FILE" | cut -f1))"
fi

echo "Standalone delivery package ready."
