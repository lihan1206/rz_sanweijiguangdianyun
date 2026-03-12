#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="$(basename "$ROOT_DIR")"
RELEASE_DIR="$ROOT_DIR/release"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_NAME="${PROJECT_NAME}_release_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="$RELEASE_DIR/$ARCHIVE_NAME"
STAGE_DIR="$(mktemp -d "/tmp/${PROJECT_NAME}_pack_XXXXXX")"
TARGET_DIR="$STAGE_DIR/$PROJECT_NAME"

cleanup() {
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

mkdir -p "$RELEASE_DIR"
mkdir -p "$TARGET_DIR"
cp -a "$ROOT_DIR"/. "$TARGET_DIR"

# 删除大体积或无关目录
find "$TARGET_DIR" -type d \
  \( -name ".git" -o -name "node_modules" -o -name ".venv" -o -name "venv" -o -name "target" \
     -o -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name "coverage" \
     -o -name ".nyc_output" -o -name "dist" -o -name "build" -o -name "release" \
     -o -name "tests" -o -name "test" -o -name "__tests__" -o -name "e2e" -o -name "cypress" \
     -o -name "playwright" \) \
  -prune -exec rm -rf {} +

# 删除测试脚本、缓存和无关材料
find "$TARGET_DIR" -type f \
  \( -name "*.pyc" -o -name "*.pyo" -o -name "*.log" -o -name ".DS_Store" -o -name ".coverage" \
     -o -name "pytest.ini" -o -name ".coveragerc" -o -name "jest.config.*" -o -name "vitest.config.*" \
     -o -name "playwright.config.*" -o -name "*test*.py" -o -name "*.spec.ts" -o -name "*.spec.tsx" \
     -o -name "*.test.ts" -o -name "*.test.tsx" -o -name "*.docx" -o -name "Prompt.md" \
     -o -name "user_rule.md" -o -name "mb.docx" \) \
  -delete

tar -czf "$ARCHIVE_PATH" -C "$STAGE_DIR" "$PROJECT_NAME"

echo "打包完成: $ARCHIVE_PATH"
du -h "$ARCHIVE_PATH" | awk '{print "包体积: "$1}'
