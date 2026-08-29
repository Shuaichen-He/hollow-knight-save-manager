# MacOS-空洞骑士存档管理器

> ### 为您的 钢魂模式 & 速通成就 保驾护航
>
> 一款给《Hollow Knight》和《Hollow Knight: Silksong》用的轻量存档管理工具（macOS）。避免频繁地手动**回档**
>
> 开游戏时一起打开它，用几个按钮即可：把当前档存成检查点、回档、以及每 15 分钟自动备份，避免手滑丢进度。
> 窗口顶部按钮可在两款游戏之间随意切换，各自存档目录独立记忆。

## 功能

- **切换游戏**：窗口顶部居中按钮，在「丝之歌」与「空洞骑士」之间随意切换；两款游戏独立记忆存档目录，并记住上次选择。
- 1号档不做修改，默认是玩家一周目的主要存档。
- **手动存档 (2→3)**：把 2 号档完整复制到 3 号档。3 号档作为可复用检查点，**保留不变**，可反复回档到它。
- **回档 (3→2)**：把 3 号档复制回 2 号档（3 号档保留），下次进游戏点 2 号档即为回档后的状态。
- **回档 (4→2)**：把 4 号档（每 15 分钟自动保存的检查点）复制回 2 号档。
- **自动保存**：后台每 15 分钟检测 2 号档是否变化，有变化则复制到 4 号档；无变化就跳过，直到你退出。
- 后台仅一个轻量线程 + 1 秒倒计时刷新，CPU/内存占用极小。

> [!WARNING]
> 温馨提示：当卡在某一 Boss 的时候，可以使用 2 和 3 档来回替换的方式避免重复开启游戏。
> 例如：2 档碎了 → 3 回档到 2 → 玩 3；3 碎了之后 → 2 存档到 3 → 玩 2，如此来回反复。
> 游戏中回档当下看不见档的情况（即回档之后依然显示碎档），但碎档后从开始界面重新进入会再次加载，回档的进度就被重新加载了，因此不用担心。

## 存档目录自动识别

脚本会自动识别两款游戏的存档目录（不同机器 steamid 不同也没关系）：

- **丝之歌**：在 `~/Library/Application Support/unity.Team-Cherry.Silksong/` 下寻找含
  `Restore_Points2` 的数字目录。
- **空洞骑士**：存档目录为 `~/Library/Application Support/unity.Team Cherry.Hollow Knight/`
  （注意目录名**带空格**、无 steamid 子目录），存档为 `user1~4.dat` 直接平铺在根目录，
  版本备份 `userX_版本号.dat` / `userX.dat.bak*` 一律不处理。

- 找到且唯一 → 直接使用；找不到 → 弹窗让你手动选择对应文件夹。
- 各游戏的选择分别写入 app 包内的
  `HollowKnightSaveManager.app/Contents/Resources/hollow_knight_save_manager.json` 记住，并记录上次使用的游戏。
- 配置文件随 app 走，**不会**在你的用户主目录下生成隐藏文件；想清除记忆，删掉 app 包内那个 json 即可。

## 下载与安装（推荐：无需 clone）

直接下载打包好的 `.pkg`，双击安装即可，**不需要 clone 仓库、也不需要本机装 Python**：

- **下载地址（GitHub Release）**：https://github.com/Shuaichen-He/hollow-knight-save-manager/releases/download/v1.0/hollow-knight-save-manager.pkg

安装后 app 位于**用户级**目录 **`~/Applications/HollowKnightSaveManager.app`**
（你个人主目录下的「应用程序」文件夹，**不需要管理员密码**），而**不是**系统级 `/Applications`。

> 未签名提示：双击 `.pkg` 若被拦截（「无法验证开发者」），右键 → **打开** 继续；
> 或用终端 `sudo installer -pkg hollow-knight-save-manager.pkg -target /`（仍装到你的 `~/Applications`）。
> 最省事的办法：把 `HollowKnightSaveManager.app` 直接拖进自己的 `~/Applications`，双击即用，连安装器都不需要。

> 该下载链接指向 GitHub Release 附件，公开/私有仓库均可（私有仓库需先登录 GitHub 再下载）。
>
> 提示：仓库于 2026-08 由 `silksong-save-manager` 更名而来，旧链接会自动跳转到新地址。

## 从源码自己构建（开发者）

需要本机有 Python 3（带 tkinter）。仓库已自带图标，构建脚本会自动处理。

```bash
git clone https://github.com/Shuaichen-He/hollow-knight-save-manager.git
cd hollow-knight-save-manager
./build_app.sh        # 生成 dist/HollowKnightSaveManager.app
./build_pkg.sh        # 生成 hollow-knight-save-manager.pkg（安装到用户级 ~/Applications）
```

`build_app.sh` 会在隔离的虚拟环境里安装 PyInstaller，把脚本冻结成**自包含 .app**
（不依赖系统 Python），并带上丝之歌风格图标。

## 使用方法

1. 开游戏的同时打开本工具（双击 .app）；默认打开上次使用的游戏，点顶部按钮可切换到另一款。
2. 进游戏点 **2 号档** 开始游玩。
3. 想存检查点：切出游戏 → 点 **手动存档 (2→3)**。
4. 想回档：点 **回档 (3→2)** 或 **回档 (4→2)**（都有确认框），回档后下次进游戏点 2 号档即可。
5. 4 号档需先触发过一次 15 分钟自动保存（或点过 3→2 之前已有自动保存）才有内容可回。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| `save_manager.py` | 主程序（界面 + 复制/自动保存逻辑，双游戏切换 + 自动探测存档目录） |
| `silksong.icns` | 丝之歌风格图标（Hornet + 检查点标记） |
| `build_app.sh` | 用 PyInstaller 冻结为自包含 .app（HollowKnightSaveManager.app，显示名「空洞骑士存档管理器」） |
| `build_pkg.sh` | 用 pkgbuild 封装 .pkg，安装到用户级 ~/Applications（无需管理员密码） |

## 备注

- 未做代码签名，分发时 macOS 会提示「无法验证开发者」。这是免费工具的常规情况，
  用上述右键打开或 `installer` 命令即可，不影响功能。
- 日志写在 `~/Library/Logs/HollowKnightSaveManager/app.log`，便于排查。
