#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Silksong 存档管理器 (unity.Team-Cherry.Silksong)

功能：
  - 手动存档按钮：把 2 号档完整复制到 3 号档（3 号档作为可重复使用的检查点，保留不变）。
  - 回档按钮（3->2）：把 3 号档完整复制到 2 号档（3 号档保留，可反复回档到同一检查点）。
  - 回档按钮（4->2）：把 4 号档（每 15 分钟自动保存的检查点）完整复制到 2 号档。
  - 自动保存：每 15 分钟检测 2 号档是否有变化，有变化则复制到 4 号档（4 号档作为时间维度的自动检查点）。

每次复制都包含：
  - 文件夹 Restore_PointsN/（还原数据，如 NODELrestoreData1.dat）
  - 存档文件 userN.dat

说明：
  - 后台仅一个轻量守护线程做 15 分钟轮询 + 一个 1 秒倒计时刷新，CPU/内存占用极小。
  - 复制采用“先删后拷”，确保目标档完全等同源档，不会残留旧文件。
  - 存档根目录自动探测：在 ~/Library/Application Support/unity.Team-Cherry.Silksong/ 下
    寻找含 Restore_Points2 的数字目录；找不到时弹窗让用户手动选择，并写入
    ~/.silksong_save_manager.json 以记住选择。
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
# 存档根目录解析（自动探测 + 配置文件覆盖 + 手动选择）
# ---------------------------------------------------------------------------
CONFIG_PATH = os.path.expanduser("~/.silksong_save_manager.json")
SEARCH_ROOT = os.path.expanduser(
    "~/Library/Application Support/unity.Team-Cherry.Silksong")

AUTOSAVE_INTERVAL = 15 * 60  # 秒


def _load_config_base():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        b = data.get("save_base")
        if b and os.path.isdir(os.path.join(b, "Restore_Points2")):
            return b
    except Exception:
        pass
    return None


def _save_config_base(base):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"save_base": base}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _detect_candidates():
    """返回所有含 Restore_Points2 的子目录（按修改时间倒序）。"""
    cands = []
    if not os.path.isdir(SEARCH_ROOT):
        return cands
    for name in os.listdir(SEARCH_ROOT):
        p = os.path.join(SEARCH_ROOT, name)
        if os.path.isdir(p) and os.path.isdir(os.path.join(p, "Restore_Points2")):
            try:
                mtime = os.path.getmtime(p)
            except OSError:
                mtime = 0
            cands.append((mtime, p))
    cands.sort(reverse=True)
    return [p for _, p in cands]


def _ask_user_for_base():
    """用隐藏 Tk 弹窗让用户选择存档根目录。"""
    root = tk.Tk()
    root.withdraw()
    try:
        msg = ("未能自动找到 Silksong 存档目录。\n"
               "请选择 unity.Team-Cherry.Silksong 下那个包含 Restore_Points2 的数字文件夹。")
        messagebox.showinfo("选择存档目录", msg)
        path = filedialog.askdirectory(
            title="选择 Silksong 存档目录（含 Restore_Points2 的文件夹）")
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    return path or None


def resolve_save_base(interactive=True):
    """解析存档根目录，返回绝对路径。

    interactive=True 时：找不到才弹窗让用户选择；失败则退出程序。
    interactive=False 时（如 --selftest）：找不到直接退出，不弹 GUI。
    """
    b = _load_config_base()
    if b:
        return b
    cands = _detect_candidates()
    if len(cands) == 1:
        return cands[0]
    if cands:
        if not interactive:
            sys.exit(2)
        # 多个候选：让用户挑（默认展示第一个）
        b = _ask_user_for_base() or cands[0]
    else:
        if not interactive:
            sys.exit(2)
        b = _ask_user_for_base()
    if not b or not os.path.isdir(os.path.join(b, "Restore_Points2")):
        messagebox.showerror(
            "无法定位存档",
            "没有找到有效的 Silksong 存档目录（需含 Restore_Points2）。程序将退出。")
        sys.exit(1)
    return b


# 模块加载时先置空，避免在 import / PyInstaller 分析 / --selftest 时误弹 GUI。
# 真正的解析在 main()（GUI）和 selftest() 中按需进行。
BASE = None


def slot_folder(n):
    return os.path.join(BASE, f"Restore_Points{n}")


def slot_dat(n):
    return os.path.join(BASE, f"user{n}.dat")


# ---------------------------------------------------------------------------
# 核心复制 / 变化检测逻辑
# ---------------------------------------------------------------------------
def copy_slot(src, dst, logfn=print):
    """把 src 号档（文件夹 + .dat）完整复制到 dst 号档，dst 被覆盖。"""
    src_f, dst_f = slot_folder(src), slot_folder(dst)
    src_d, dst_d = slot_dat(src), slot_dat(dst)

    if not os.path.isdir(src_f):
        raise FileNotFoundError(f"源文件夹不存在: {src_f}")
    if not os.path.isfile(src_d):
        raise FileNotFoundError(f"源存档文件不存在: {src_d}")

    # 文件夹：先删后拷，保证 dst 完全等同 src（不残留旧文件）
    if os.path.exists(dst_f):
        shutil.rmtree(dst_f)
    shutil.copytree(src_f, dst_f)

    # .dat 文件：copy2 保留时间戳等元数据
    shutil.copy2(src_d, dst_d)
    logfn(f"已复制 {src} 号档 -> {dst} 号档")


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
    for p in (slot_folder(n), slot_dat(n)):
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        st = os.stat(fp)
                        items.append((fp, st.st_size, st.st_mtime_ns))
                    except OSError:
                        pass
        elif os.path.isfile(p):
            try:
                st = os.stat(p)
                items.append((p, st.st_size, st.st_mtime_ns))
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
    def __init__(self, root):
        self.root = root
        root.title("Silksong 存档管理器")
        root.geometry("400x360")
        root.resizable(False, False)

        self.state = {
            "running": True,
            "next_check": time.time() + AUTOSAVE_INTERVAL,
            "last_sig": None,
            "lock": threading.Lock(),
        }

        self.status_var = tk.StringVar(value="准备就绪")
        tk.Label(root, textvariable=self.status_var, fg="#1a59d6",
                 wraplength=370, font=("Helvetica", 11, "bold")).pack(pady=(10, 2))
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
        self.log_msg("工具已启动。2 号档=当前游玩档；3 号档=手动检查点；4 号档... 4 号档=每 15 分钟自动保存。")
        self._check_paths()

        self.autosaver = Autosaver(self.log_msg, self.state)
        self.autosaver.start()
        self.tick()
        root.protocol("WM_DELETE_WINDOW", self.quit_app)

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
            if not os.path.isdir(slot_folder(n)):
                self.log_msg(f"警告：{slot_folder(n)} 不存在")
            if not os.path.isfile(slot_dat(n)):
                self.log_msg(f"提示：{slot_dat(n)} 不存在（自动存档时会创建）")

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
# 自检（不触碰真实存档，复制进临时目录验证逻辑）
# ---------------------------------------------------------------------------
def selftest():
    global BASE
    import tempfile
    import filecmp

    # 非交互解析真实存档根目录（用于拷贝样本，不弹 GUI）
    BASE = resolve_save_base(interactive=False)
    tmp = tempfile.mkdtemp(prefix="ssl_test_")
    print("selftest base:", tmp)
    for n in (2, 3, 4):
        shutil.copytree(slot_folder(n), os.path.join(tmp, f"Restore_Points{n}"))
        if os.path.isfile(slot_dat(n)):
            shutil.copy2(slot_dat(n), os.path.join(tmp, f"user{n}.dat"))

    saved = BASE
    BASE = tmp
    try:
        copy_slot(2, 3, print)
        dircmp = filecmp.dircmp(os.path.join(tmp, "Restore_Points2"),
                                os.path.join(tmp, "Restore_Points3"))
        assert not dircmp.left_only and not dircmp.right_only and not dircmp.diff_files, \
            f"文件夹内容不一致: {dircmp.report()}"
        assert filecmp.cmp(os.path.join(tmp, "user2.dat"),
                           os.path.join(tmp, "user3.dat"), shallow=False), "dat 不一致"
        print("OK: 2 -> 3 复制正确")

        copy_slot(3, 2, print)
        dircmp = filecmp.dircmp(os.path.join(tmp, "Restore_Points3"),
                                os.path.join(tmp, "Restore_Points2"))
        assert not dircmp.left_only and not dircmp.right_only and not dircmp.diff_files, \
            "3->2 文件夹内容不一致"
        print("OK: 3 -> 2 复制正确")

        copy_slot(2, 4, print)
        dircmp = filecmp.dircmp(os.path.join(tmp, "Restore_Points2"),
                                os.path.join(tmp, "Restore_Points4"))
        assert not dircmp.left_only and not dircmp.right_only and not dircmp.diff_files, \
            "2->4 文件夹内容不一致"
        print("OK: 2 -> 4 复制正确")

        s1 = slot_signature(2)
        with open(slot_dat(2), "ab") as f:
            f.write(b"x")
        s2 = slot_signature(2)
        assert s1 != s2, "修改后应检测到变化"
        print("OK: 变化检测生效")
        print("ALL TESTS PASSED")
    finally:
        BASE = saved
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Silksong 存档管理器")
    parser.add_argument("--selftest", action="store_true",
                        help="运行逻辑自检（不修改真实存档）")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    # GUI 模式：解析存档根目录（必要时弹窗让用户选择并记住）
    global BASE
    BASE = resolve_save_base(interactive=True)
    _save_config_base(BASE)

    # 运行日志写到用户可写位置（安装到 /Applications 后 Resources 不可写）
    log_dir = os.path.expanduser("~/Library/Logs/SilksongSaveManager")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "app.log")
        sys.stdout = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
    except Exception:
        pass

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
