#!/usr/bin/env bash
# 把 dist/SilksongSaveManager.app 封装成 macOS 安装包 .pkg，
# 安装到 /Applications。产物：silksong-save-manager.pkg
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

APP="$REPO/dist/SilksongSaveManager.app"
PKG="$REPO/silksong-save-manager.pkg"

if [ ! -d "$APP" ]; then
  echo "错误：未找到 $APP，请先运行 ./build_app.sh" >&2
  exit 1
fi

echo "==> 构建组件包（安装到 /Applications）"
rm -f "$PKG"
pkgbuild \
  --component "$APP" \
  --install-location /Applications \
  --identifier com.silksong.savemanager \
  --version 1.0.0 \
  --preserve-xattr \
  "$PKG"

echo "==> 完成：$PKG"
ls -lh "$PKG"
