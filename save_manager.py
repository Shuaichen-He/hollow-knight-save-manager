#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
空洞骑士存档管理器（Hollow Knight / Silksong 双游戏支持）

功能：
  - 顶部居中「切换游戏」按钮：在 丝之歌(Silksong) 与 空洞骑士(Hollow Knight) 之间随意切换，
    每个游戏独立记忆自己的存档目录，并记住上次选择的游戏。
  - 手动存档按钮（2->3）：把 2 号档完整复制到 3 号档（3 号档作为可重复使用的检查点，保留不变）。
  - 回档按钮（3->2）：把 3 号档完整复制到 2 号档（3 号档保留，可反复回档到同一检查点）。
  - 回档按钮（4->2）：把 4 号档（每 15 分钟自动保存的检查点）完整复制到 2 号档。
  - 自动保存：每 15 分钟检测 2 号档是否有变化，有变化则复制到 4 号档。

两种游戏的存档结构：
  - 丝之歌 (unity.Team-Cherry.Silksong/<steamid>/)：Restore_PointsN/ 文件夹 + userN.dat
  - 空洞骑士 (unity.Team Cherry.Hollow Knight/)：只有 userN.dat 平铺在根目录（无 Restore_Points）
    空洞骑士的 userX_版本号.dat / userX.dat.bak* 等版本备份文件一律不处理，只操作 userN.dat。

说明：
  - 后台仅一个轻量守护线程做 15 分钟轮询 + 一个 1 秒倒计时刷新，CPU/内存占用极小。
  - 复制采用“先删后拷”，确保目标档完全等同源档，不会残留旧文件。
  - 存档根目录自动探测；找不到时弹窗让用户手动选择，并把选择写入
    app 包内的 hollow_knight_save_manager.json（随 app 走，不放在用户目录）。
"""

import os
import sys
import json
import shutil
import threading
import time
import argparse

import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog

# ---------------------------------------------------------------------------
# 游戏定义
# ---------------------------------------------------------------------------
GAMES = {
    "silksong": {
        "name": "丝之歌",
        "style": "silksong",  # Restore_PointsN/ + userN.dat
        "search_root": os.path.expanduser(
            "~/Library/Application Support/unity.Team-Cherry.Silksong"),
    },
    "hollowknight": {
        "name": "空洞骑士",
        "style": "flat",  # 只有 userN.dat 平铺
        "search_root": os.path.expanduser(
            "~/Library/Application Support/unity.Team Cherry.Hollow Knight"),
    },
}


def _app_resources_dir():
    """配置文件的存放目录：随 app 走，放在 app 包内的 Resources 里。

    冻结后的 .app：sys.executable 位于 Contents/MacOS 下，取上一级的 Resources。
    源码直接运行时：放在脚本同目录。
    注意：若 app 装在只读位置（如系统级 /Applications），写入会失败，
    此时不持久化（每次启动重新探测），属可接受的退化行为。
    """
    if getattr(sys, "frozen", False):
        return os.path.normpath(
            os.path.join(os.path.dirname(sys.executable), "..", "Resources"))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_app_resources_dir(), "hollow_knight_save_manager.json")

AUTOSAVE_INTERVAL = 15 * 60  # 秒

# 当前游戏 / 当前存档根目录（模块加载时置空，真正解析在 main()/selftest() 中按需进行）
CURRENT_GAME = None
BASE = None
GAME_BASES = {}  # game -> save_base


# ---------------------------------------------------------------------------
# 配置文件读写（多游戏结构，兼容旧的 {"save_base": ...} 格式）
# ---------------------------------------------------------------------------
def _load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "games" in data:
            return data
        # 旧格式 {"save_base": "..."} -> 迁移为丝之歌的配置
        if data.get("save_base"):
            return {"games": {"silksong": {"save_base": data["save_base"]}},
                    "last_game": "silksong"}
    except Exception:
        pass
    return {"games": {}, "last_game": None}


def _save_config():
    cfg = {"games": {}, "last_game": CURRENT_GAME}
    for g in GAMES:
        if GAME_BASES.get(g):
            cfg["games"][g] = {"save_base": GAME_BASES[g]}
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        # 常见于 app 装在只读位置（如系统级 /Applications）
        print(f"警告：无法把存档路径写入配置（{CONFIG_PATH}）：{e}")


# ---------------------------------------------------------------------------
# 存档根目录解析（自动探测 + 配置文件覆盖 + 手动选择）
# ---------------------------------------------------------------------------
def _validate_base(game, b):
    """校验某个候选目录是否是该游戏的存档根目录。"""
    if not b:
        return False
    if game == "silksong":
        return os.path.isdir(os.path.join(b, "Restore_Points2"))
    # hollowknight：目录存在且含 user2.dat
    return os.path.isfile(os.path.join(b, "user2.dat"))


def _detect_candidates(game):
    """返回该游戏所有候选存档根目录（按修改时间倒序）。"""
    root = GAMES[game]["search_root"]
    if game == "silksong":
        cands = []
        if not os.path.isdir(root):
            return cands
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if os.path.isdir(p) and os.path.isdir(os.path.join(p, "Restore_Points2")):
                try:
                    mtime = os.path.getmtime(p)
                except OSError:
                    mtime = 0
                cands.append((mtime, p))
        cands.sort(reverse=True)
        return [p for _, p in cands]
    # hollowknight：存档根目录就是 search_root 本身
    if os.path.isfile(os.path.join(root, "user2.dat")):
        return [root]
    return []


def _ask_user_for_base(game):
    """用隐藏 Tk 弹窗让用户选择存档根目录。"""
    info = GAMES[game]
    root = tk.Tk()
    root.withdraw()
    try:
        if game == "silksong":
            messagebox.showinfo(
                "选择存档目录",
                f"未能自动找到{info['name']}存档目录。\n"
                "请选择 unity.Team-Cherry.Silksong 下那个包含 Restore_Points2 的数字文件夹。")
            path = filedialog.askdirectory(
                title="选择 Silksong 存档目录（含 Restore_Points2 的文件夹）")
        else:
            messagebox.showinfo(
                "选择存档目录",
                f"未能自动找到{info['name']}存档目录。\n"
                "请选择包含 user2.dat 的存档文件夹。")
            path = filedialog.askdirectory(
                title="选择 Hollow Knight 存档目录（含 user2.dat 的文件夹）")
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    return path or None


def resolve_save_base(game, interactive=True):
    """解析指定游戏的存档根目录，返回绝对路径，并记入 GAME_BASES。

    interactive=True 时：找不到才弹窗让用户选择；失败则退出程序。
    interactive=False 时（如 --selftest）：找不到直接退出，不弹 GUI。
    """
    global GAME_BASES
    b = GAME_BASES.get(game)
    if b and _validate_base(game, b):
        return b
    cands = _detect_candidates(game)
    if len(cands) == 1:
        GAME_BASES[game] = cands[0]
        return cands[0]
    if cands:
        if not interactive:
            sys.exit(2)
        # 多个候选：让用户挑（默认展示第一个）
        b = _ask_user_for_base(game) or cands[0]
    else:
        if not interactive:
            sys.exit(2)
        b = _ask_user_for_base(game)
    if not b or not _validate_base(game, b):
        messagebox.showerror(
            "无法定位存档",
            f"没有找到有效的{GAMES[game]['name']}存档目录。程序将退出。")
        sys.exit(1)
    GAME_BASES[game] = b
    return b


def _game_style():
    return GAMES[CURRENT_GAME]["style"]


def slot_folder(n):
    """丝之歌结构下返回 Restore_PointsN 路径；空洞骑士（flat）返回 None。"""
    if _game_style() == "silksong":
        return os.path.join(BASE, f"Restore_Points{n}")
    return None


def slot_dat(n):
    return os.path.join(BASE, f"user{n}.dat")


# ---------------------------------------------------------------------------
# 核心复制 / 变化检测逻辑
# ---------------------------------------------------------------------------
def copy_slot(src, dst, logfn=print):
    """把 src 号档完整复制到 dst 号档，dst 被覆盖。

    丝之歌：文件夹 Restore_PointsN/ + userN.dat；空洞骑士：仅 userN.dat。
    """
    gname = GAMES[CURRENT_GAME]["name"]
    src_d, dst_d = slot_dat(src), slot_dat(dst)
    if not os.path.isfile(src_d):
        raise FileNotFoundError(f"源存档文件不存在: {src_d}")

    if _game_style() == "silksong":
        src_f, dst_f = slot_folder(src), slot_folder(dst)
        if not os.path.isdir(src_f):
            raise FileNotFoundError(f"源文件夹不存在: {src_f}")
        # 文件夹：先删后拷，保证 dst 完全等同 src（不残留旧文件）
        if os.path.exists(dst_f):
            shutil.rmtree(dst_f)
        shutil.copytree(src_f, dst_f)

    # .dat 文件：copy2 保留时间戳等元数据
    shutil.copy2(src_d, dst_d)
    logfn(f"[{gname}] 已复制 {src} 号档 -> {dst} 号档")


def copy_slot_retry(src, dst, logfn=print, retries=2):
    """带重试的复制（游戏运行时偶发读到半写入文件时自动重试）。"""
    last = None
    for i in range(retries + 1):
        try:
            copy_slot(src, dst, logfn)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries:
                time.sleep(1.0)
    logfn(f"复制失败: {last}")
    raise last


def slot_signature(n):
    """返回 2 号档当前的“指纹”（文件大小+修改时间）。用于检测是否变化。"""
    items = []
    f = slot_folder(n)
    if f and os.path.isdir(f):
        for root, _, files in os.walk(f):
            for name in files:
                fp = os.path.join(root, name)
                try:
                    st = os.stat(fp)
                    items.append((fp, st.st_size, st.st_mtime_ns))
                except OSError:
                    pass
    d = slot_dat(n)
    if os.path.isfile(d):
        try:
            st = os.stat(d)
            items.append((d, st.st_size, st.st_mtime_ns))
        except OSError:
            pass
    return tuple(sorted(items))


# ---------------------------------------------------------------------------
# 自动保存线程
# ---------------------------------------------------------------------------
class Autosaver(threading.Thread):
    def __init__(self, logfn, state):
        super().__init__(daemon=True)
        self.logfn = logfn
        self.state = state
        self.stop_event = threading.Event()

    def run(self):
        st = self.state
        with st["lock"]:
            st["last_sig"] = slot_signature(2)
        while not self.stop_event.is_set():
            with st["lock"]:
                st["next_check"] = time.time() + AUTOSAVE_INTERVAL
            # 分片等待，便于随时响应退出
            if self.stop_event.wait(AUTOSAVE_INTERVAL):
                break
            if self.stop_event.is_set():
                break
            cur = slot_signature(2)
            with st["lock"]:
                changed = cur != st["last_sig"]
            if changed:
                try:
                    copy_slot_retry(2, 4, self.logfn)
                    with st["lock"]:
                        st["last_sig"] = cur
                except Exception as e:  # noqa: BLE001
                    self.logfn(f"自动保存出错: {e}")
            else:
                self.logfn("15 分钟检测：2 号档无变化，跳过")
        self.logfn("自动保存线程已停止")


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class App:
    def __init__(self, root, game):
        global BASE, CURRENT_GAME
        CURRENT_GAME = game
        self.root = root
        self._apply_title()
        root.geometry("430x410")
        root.resizable(False, False)

        self.state = {
            "running": True,
            "next_check": time.time() + AUTOSAVE_INTERVAL,
            "last_sig": None,
            "lock": threading.Lock(),
        }

        # 顶部居中：切换游戏按钮
        self.game_btn = tk.Button(root, text=self._game_btn_text(), width=30,
                                  command=self.switch_game)
        self.game_btn.pack(pady=(12, 2))

        self.status_var = tk.StringVar(value="准备就绪")
        tk.Label(root, textvariable=self.status_var, fg="#1a59d6",
                 wraplength=400, font=("Helvetica", 11, "bold")).pack(pady=(6, 2))
        self.count_var = tk.StringVar(value="下次自动保存检查：--:--")
        tk.Label(root, textvariable=self.count_var, fg="#555555").pack()

        frm = tk.Frame(root)
        frm.pack(pady=10)
        tk.Button(frm, text="手动存档 (2→3)", width=15,
                  command=self.manual_save).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(frm, text="回档 (3→2)", width=15,
                  command=self.rollback).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(frm, text="回档 (4→2)", width=15,
                  command=self.rollback4).grid(row=1, column=0, padx=5, pady=5)
        tk.Button(frm, text="退出", width=15,
                  command=self.quit_app).grid(row=1, column=1, padx=5, pady=5)

        tk.Label(root, text="操作日志", fg="#333333").pack(anchor="w", padx=10)
        self.log = scrolledtext.ScrolledText(
            root, height=9, wrap=tk.WORD, font=("Menlo", 9))
        self.log.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 10))

        self.log_msg(f"存档目录：{BASE}")
        self.log_msg(f"当前游戏：{GAMES[CURRENT_GAME]['name']}。"
                     "2 号档=当前游玩档；3 号档=手动检查点；4 号档=每 15 分钟自动保存。")
        self._check_paths()

        self.autosaver = Autosaver(self.log_msg, self.state)
        self.autosaver.start()
        self.tick()
        root.protocol("WM_DELETE_WINDOW", self.quit_app)

    def _apply_title(self):
        self.root.title("空洞骑士存档管理器")

    def _game_btn_text(self):
        other = "空洞骑士" if CURRENT_GAME == "silksong" else "丝之歌"
        return f"当前游戏：{GAMES[CURRENT_GAME]['name']}　（点击切换到 {other}）"

    # ---- 日志（后台线程安全：统一切回主线程写 UI）----
    def log_msg(self, msg):
        self.root.after(0, self._log_msg_main, msg)

    def _log_msg_main(self, msg):
        try:
            ts = time.strftime("%H:%M:%S")
            self.log.insert(tk.END, f"[{ts}] {msg}\n")
            self.log.see(tk.END)
        except Exception:  # noqa: BLE001
            pass

    def _check_paths(self):
        for n in (2, 3, 4):
            if _game_style() == "silksong":
                if not os.path.isdir(slot_folder(n)):
                    self.log_msg(f"警告：{slot_folder(n)} 不存在")
            if not os.path.isfile(slot_dat(n)):
                self.log_msg(f"提示：{slot_dat(n)} 不存在（自动存档时会创建）")

    # ---- 切换游戏 ----
    def switch_game(self):
        global BASE, CURRENT_GAME
        new = "hollowknight" if CURRENT_GAME == "silksong" else "silksong"
        old_name = GAMES[CURRENT_GAME]["name"]
        GAME_BASES[CURRENT_GAME] = BASE
        try:
            CURRENT_GAME = new
            BASE = resolve_save_base(new, interactive=True)
        except SystemExit:
            # 用户在新游戏上没有有效存档且取消选择 -> 切回原游戏
            CURRENT_GAME = "hollowknight" if new == "silksong" else "silksong"
            BASE = GAME_BASES.get(CURRENT_GAME) or BASE
            self.log_msg("切换已取消：未能定位目标游戏存档。")
            return
        GAME_BASES[new] = BASE
        _save_config()
        # 刷新自动保存基准（换游戏后指纹立即对准新游戏的 2 号档）
        with self.state["lock"]:
            self.state["last_sig"] = slot_signature(2)
            self.state["next_check"] = time.time() + AUTOSAVE_INTERVAL
        self._apply_title()
        self.game_btn.config(text=self._game_btn_text())
        self.status_var.set(f"已切换到 {GAMES[CURRENT_GAME]['name']} 存档")
        self.log_msg(f"已从 {old_name} 切换到 {GAMES[CURRENT_GAME]['name']}，存档目录：{BASE}")
        self._check_paths()

    # ---- 按钮动作 ----
    def manual_save(self):
        try:
            copy_slot_retry(2, 3, self.log_msg)
            self.status_var.set("已手动存档：2 号档 -> 3 号档（3 号档保留）")
            self.log_msg("手动存档完成。游戏内切回 2 号档继续游玩即可。")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("手动存档失败", str(e))
            self.log_msg(f"手动存档失败: {e}")

    def rollback(self):
        ok = messagebox.askyesno(
            "确认回档",
            "将用 3 号档覆盖 2 号档（当前 2 号档的进度会被 3 号档取代）。\n"
            "3 号档会保留，可再次回档到同一检查点。是否继续？")
        if not ok:
            self.log_msg("已取消回档。")
            return
        try:
            copy_slot_retry(3, 2, self.log_msg)
            with self.state["lock"]:
                self.state["last_sig"] = slot_signature(2)
            self.status_var.set("已回档：3 号档 -> 2 号档")
            self.log_msg("回档完成。下次进游戏点 2 号档即为回档后的状态。")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("回档失败", str(e))
            self.log_msg(f"回档失败: {e}")

    def rollback4(self):
        ok = messagebox.askyesno(
            "确认回档",
            "将用 4 号档（每 15 分钟自动保存的检查点）覆盖 2 号档。\n"
            "当前 2 号档的进度会被 4 号档取代。是否继续？")
        if not ok:
            self.log_msg("已取消回档。")
            return
        try:
            copy_slot_retry(4, 2, self.log_msg)
            with self.state["lock"]:
                self.state["last_sig"] = slot_signature(2)
            self.status_var.set("已回档：4 号档 -> 2 号档")
            self.log_msg("回档完成。下次进游戏点 2 号档即为回档后的状态。")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("回档失败", str(e))
            self.log_msg(f"回档失败: {e}")

    # ---- 倒计时刷新 ----
    def tick(self):
        if not self.state["running"]:
            return
        with self.state["lock"]:
            nxt = self.state["next_check"]
        rem = max(0, int(nxt - time.time()))
        mm, ss = divmod(rem, 60)
        self.count_var.set(f"下次自动保存检查：{mm:02d}:{ss:02d}")
        self.root.after(1000, self.tick)

    def quit_app(self):
        self.state["running"] = False
        try:
            self.autosaver.stop_event.set()
        except Exception:  # noqa: BLE001
            pass
        self.log_msg("正在退出…")
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# 自检（合成临时目录验证两种存档结构，不触碰真实存档）
# ---------------------------------------------------------------------------
def _test_copy_logic(base, check_folder):
    import filecmp

    def same_dat(a, b):
        return filecmp.cmp(os.path.join(base, f"user{a}.dat"),
                           os.path.join(base, f"user{b}.dat"), shallow=False)

    def same_folder(a, b):
        if not check_folder:
            return True
        d = filecmp.dircmp(os.path.join(base, f"Restore_Points{a}"),
                           os.path.join(base, f"Restore_Points{b}"))
        return not d.left_only and not d.right_only and not d.diff_files

    copy_slot(2, 3, print)
    assert same_dat(2, 3), "2->3 dat 不一致"
    assert same_folder(2, 3), "2->3 文件夹内容不一致"
    print("OK: 2 -> 3 复制正确")

    copy_slot(3, 2, print)
    assert same_dat(3, 2), "3->2 dat 不一致"
    assert same_folder(3, 2), "3->2 文件夹内容不一致"
    print("OK: 3 -> 2 复制正确")

    copy_slot(2, 4, print)
    assert same_dat(2, 4), "2->4 dat 不一致"
    assert same_folder(2, 4), "2->4 文件夹内容不一致"
    print("OK: 2 -> 4 复制正确")

    s1 = slot_signature(2)
    with open(slot_dat(2), "ab") as f:
        f.write(b"x")
    s2 = slot_signature(2)
    assert s1 != s2, "修改后应检测到变化"
    print("OK: 变化检测生效")


def selftest():
    global BASE, CURRENT_GAME
    import tempfile

    tmp = tempfile.mkdtemp(prefix="ssl_test_")
    print("selftest base:", tmp)
    try:
        # ---- 丝之歌结构（Restore_PointsN + userN.dat）----
        sbase = os.path.join(tmp, "silksong")
        os.makedirs(sbase)
        for n in (2, 3, 4):
            os.makedirs(os.path.join(sbase, f"Restore_Points{n}"))
            with open(os.path.join(sbase, f"Restore_Points{n}", "NODELrestoreData1.dat"),
                      "w") as f:
                f.write(f"restore-{n}")
            with open(os.path.join(sbase, f"user{n}.dat"), "w") as f:
                f.write(f"user-{n}")
        BASE, CURRENT_GAME = sbase, "silksong"
        print("== 测试 silksong 结构 ==")
        _test_copy_logic(sbase, check_folder=True)
        print("OK: silksong 结构全部通过")

        # ---- 空洞骑士结构（仅 userN.dat 平铺）----
        hbase = os.path.join(tmp, "hollowknight")
        os.makedirs(hbase)
        for n in (2, 3, 4):
            with open(os.path.join(hbase, f"user{n}.dat"), "w") as f:
                f.write(f"hk-user-{n}")
        BASE, CURRENT_GAME = hbase, "hollowknight"
        print("== 测试 hollowknight 结构 ==")
        _test_copy_logic(hbase, check_folder=False)
        print("OK: hollowknight 结构全部通过")

        print("ALL TESTS PASSED")
    finally:
        BASE = None
        CURRENT_GAME = None
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="空洞骑士存档管理器（Hollow Knight / Silksong 双游戏）")
    parser.add_argument("--selftest", action="store_true",
                        help="运行逻辑自检（不修改真实存档）")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    # GUI 模式：加载配置，恢复上次选择的游戏并解析其存档根目录
    global BASE, CURRENT_GAME
    cfg = _load_config()
    for g, info in cfg.get("games", {}).items():
        if g in GAMES and info.get("save_base"):
            GAME_BASES[g] = info["save_base"]
    initial = cfg.get("last_game")
    if initial not in GAMES:
        initial = "silksong"
    CURRENT_GAME = initial
    BASE = resolve_save_base(CURRENT_GAME, interactive=True)
    GAME_BASES[CURRENT_GAME] = BASE
    _save_config()

    # 运行日志写到用户可写位置（安装到 /Applications 后 Resources 不可写）
    log_dir = os.path.expanduser("~/Library/Logs/HollowKnightSaveManager")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "app.log")
        sys.stdout = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
    except Exception:
        pass

    root = tk.Tk()
    App(root, CURRENT_GAME)
    root.mainloop()


if __name__ == "__main__":
    main()
