#!/usr/bin/env bash
# 把 save_manager.py 冻结为自包含的 macOS .app（不依赖系统 Python）。
# 产物：dist/SilksongSaveManager.app
set -euo pipefail

# 仓库根目录（脚本所在目录）
REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

# 隔离的 managed Python（自带 tkinter）
PY="/Users/hsc/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
VENV="/Users/hsc/.workbuddy/binaries/python/envs/default"

echo "==> 准备隔离 venv: $VENV"
if [ ! -x "$VENV/bin/python3" ]; then
  "$PY" -m venv "$VENV"
fi

echo "==> 安装/更新 PyInstaller"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet pyinstaller

echo "==> 让出旧构建产物（重命名而非删除，避免触发批量删除保护）"
[ -e "$REPO/dist" ] && mv "$REPO/dist" "$REPO/dist.bak.$$"
[ -e "$REPO/build" ] && mv "$REPO/build" "$REPO/build.bak.$$"
[ -e "$REPO/SilksongSaveManager.spec" ] && mv "$REPO/SilksongSaveManager.spec" "$REPO/SilksongSaveManager.spec.bak.$$"

echo "==> 运行 PyInstaller"
"$VENV/bin/pyinstaller" \
  --windowed \
  --name SilksongSaveManager \
  --icon "$REPO/silksong.icns" \
  --osx-bundle-identifier com.silksong.savemanager \
  --clean \
  "$REPO/save_manager.py"

echo "==> 完成：dist/SilksongSaveManager.app"
ls -lh "$REPO/dist/SilksongSaveManager.app"
