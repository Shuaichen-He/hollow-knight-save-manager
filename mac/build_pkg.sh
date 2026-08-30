#!/usr/bin/env bash
# 把 dist/HollowKnightSaveManager.app 封装成 macOS 安装包 .pkg，
# 安装到用户级 ~/Applications（个人主目录下的应用程序，而非系统级 /Applications）。
# 产物：hollow-knight-save-manager.pkg
#
# 注意：
#   - 组件 pkg 的安装路径在构建时写死为当前用户的 $HOME/Applications。
#     若是分发给别人，建议直接分发 .app（见 README），而非依赖此 pkg 的路径。
#   - 用 `installer` 命令安装时仍需要管理员密码（installer 本身须以 root 运行），
#     但 app 会落到用户目录；最省事的办法是手动把 .app 拖进 ~/Applications（免密码）。
set -eu
set -o pipefail 2>/dev/null || true

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

APP="$REPO/dist/HollowKnightSaveManager.app"
PKG="$REPO/hollow-knight-save-manager.pkg"

if [ ! -d "$APP" ]; then
  echo "错误：未找到 $APP，请先运行 ./build_app.sh" >&2
  exit 1
fi

echo "==> 构建组件包（安装到用户级 ~/Applications）"
rm -f "$PKG"
pkgbuild \
  --component "$APP" \
  --install-location "$HOME/Applications" \
  --identifier com.hollowknight.savemanager \
  --version 3.0.0 \
  --preserve-xattr \
  "$PKG"

echo "==> 完成：$PKG"
ls -lh "$PKG"
