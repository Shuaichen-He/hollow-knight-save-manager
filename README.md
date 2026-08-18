# Silksong 存档管理器

一个给《Hollow Knight: Silksong》用的轻量存档管理工具（macOS）。开游戏时一起打开它，
用几个按钮即可：把当前档存成检查点、回档、以及每 15 分钟自动备份，避免手滑丢进度。

> 灵感来自频繁「回档重来」的游玩方式：2 号档 = 当前游玩档；3 号档 = 手动检查点；
> 4 号档 = 每 15 分钟自动保存的时间检查点。

## 功能

- **手动存档 (2→3)**：把 2 号档完整复制到 3 号档。3 号档作为可复用检查点，**保留不变**，可反复回档到它。
- **回档 (3→2)**：把 3 号档复制回 2 号档（3 号档保留），下次进游戏点 2 号档即为回档后的状态。
- **回档 (4→2)**：把 4 号档（每 15 分钟自动保存的检查点）复制回 2 号档。
- **自动保存**：后台每 15 分钟检测 2 号档是否变化，有变化则复制到 4 号档；无变化就跳过，直到你退出。
- 后台仅一个轻量线程 + 1 秒倒计时刷新，CPU/内存占用极小。

## 存档目录自动识别

脚本会自动在 `~/Library/Application Support/unity.Team-Cherry.Silksong/` 下寻找含
`Restore_Points2` 的数字目录（不同机器 steamid 不同也没关系）。

- 找到且唯一 → 直接使用，并写入 `~/.silksong_save_manager.json` 记住。
- 找不到 → 弹窗让你手动选择那个数字文件夹。

## 怎么拿到并运行

### 方式 A：下载现成 .pkg（推荐给普通用户）

1. 到 Release 页下载 `silksong-save-manager.pkg`。
2. 安装后，app 位于 **`/Applications/SilksongSaveManager.app`**（由 pkg 的安装位置决定）。
   - 是否把它留在 `/Applications` 由你自己决定：你也可以让 `.app` 待在任意位置（如下载文件夹）直接双击使用，
     或自行拖入 `/Applications`、拖到程序坞。它不依赖安装路径，放到哪都能跑。
3. 如何安装（未签名 pkg 的两种做法）：
   - **命令行（最稳，保证真正落到 `/Applications`）**：终端执行
     ```bash
     sudo installer -pkg silksong-save-manager.pkg -target /
     ```
   - **图形界面**：双击 `.pkg` 时若被拦截（「无法验证开发者」），右键 → **打开** 继续。
     注意：未签名的 pkg 在纯图形安装流程下偶尔只登记回执、未真正落盘，遇到这种情况改用上面的命令行即可。

### 方式 B：从源码自己构建（开发者）

需要本机有 Python 3（带 tkinter）。仓库已自带图标，构建脚本会自动处理。

```bash
git clone <你的仓库地址>
cd silksong-save-manager
./build_app.sh        # 生成 dist/SilksongSaveManager.app
./build_pkg.sh        # 生成 silksong-save-manager.pkg（安装到 /Applications）
```

`build_app.sh` 会在隔离的虚拟环境里安装 PyInstaller，把脚本冻结成**自包含 .app**
（不依赖系统 Python），并带上丝之歌风格图标。

## 使用方法

1. 开游戏的同时打开本工具（双击 .app）。
2. 进游戏点 **2 号档** 开始游玩。
3. 想存检查点：切出游戏 → 点 **手动存档 (2→3)**。
4. 想回档：点 **回档 (3→2)** 或 **回档 (4→2)**（都有确认框），回档后下次进游戏点 2 号档即可。
5. 4 号档需先触发过一次 15 分钟自动保存（或点过 3→2 之前已有自动保存）才有内容可回。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `save_manager.py` | 主程序（界面 + 复制/自动保存逻辑，含自动探测存档目录） |
| `silksong.icns` | 丝之歌风格图标（Hornet + 检查点标记） |
| `build_app.sh` | 用 PyInstaller 冻结为自包含 .app |
| `build_pkg.sh` | 用 pkgbuild 封装 .pkg 安装到 /Applications |

## 备注

- 未做代码签名，分发时 macOS 会提示「无法验证开发者」。这是免费工具的常规情况，
  用上述右键打开或 `installer` 命令即可，不影响功能。
- 日志写在 `~/Library/Logs/SilksongSaveManager/app.log`，便于排查。
