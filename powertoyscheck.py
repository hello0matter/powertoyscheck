import base64
import json
import os
import shutil
import subprocess
import sys
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_TITLE = "PowerToys 启动区配置管理"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def default_config_path() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local / "Microsoft" / "PowerToys" / "Workspaces" / "workspaces.json"


def default_launcher_path() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local / "PowerToys" / "PowerToys.WorkspacesLauncher.exe"


def new_guid() -> str:
    return "{" + str(uuid.uuid4()) + "}"


def is_python_path(path: str) -> bool:
    return Path(path or "").name.lower() in {"python.exe", "pythonw.exe"}


def pythonw_path(path: str) -> str:
    p = Path(path)
    if p.name.lower() == "python.exe":
        return str(p.with_name("pythonw.exe"))
    return path


def expanded_path(path: str) -> Path:
    return Path(os.path.expandvars(path or "")).expanduser()


def app_path_missing(app: dict) -> bool:
    path = app.get("application-path", "")
    if not path:
        return True
    return not expanded_path(path).exists()


def ps_single(value: str) -> str:
    return value.replace("'", "''")


class WorkspaceStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = {"workspaces": []}

    def load(self) -> None:
        if not self.path.exists():
            self.data = {"workspaces": []}
            return
        with self.path.open("r", encoding="utf-8-sig") as f:
            self.data = json.load(f)
        self.data.setdefault("workspaces", [])

    def backup(self) -> Path:
        backup_dir = self.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / f"workspaces-{stamp}.json"
        if self.path.exists():
            backup.write_bytes(self.path.read_bytes())
        else:
            backup.write_text(json.dumps({"workspaces": []}, indent=2), encoding="utf-8")
        return backup

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        backup = self.backup()
        temp = self.path.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        temp.replace(self.path)
        return backup

    @property
    def workspaces(self) -> list[dict]:
        return self.data.setdefault("workspaces", [])

    @property
    def backup_dir(self) -> Path:
        return self.path.parent / "powertoyscheck-backups"


class PowerToysCheck(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(1040, 680)

        self.store = WorkspaceStore(default_config_path())
        self.current_workspace_index: int | None = None
        self.current_app_index: int | None = None

        self._vars()
        self._build()
        self.reload()

    def _vars(self) -> None:
        self.config_path = tk.StringVar(value=str(default_config_path()))
        self.status = tk.StringVar(value="就绪")

        self.ws_name = tk.StringVar()
        self.ws_shortcut = tk.BooleanVar(value=True)
        self.ws_move_existing = tk.BooleanVar(value=True)

        self.app_application = tk.StringVar()
        self.app_title = tk.StringVar()
        self.app_path = tk.StringVar()
        self.app_args = tk.StringVar()
        self.app_elevated = tk.BooleanVar(value=False)
        self.app_can_elevate = tk.BooleanVar(value=False)
        self.app_minimized = tk.BooleanVar(value=False)
        self.app_maximized = tk.BooleanVar(value=False)
        self.app_monitor = tk.StringVar(value="1")
        self.app_filter = tk.StringVar()
        self.show_missing_only = tk.BooleanVar(value=False)
        self.pos_x = tk.StringVar(value="0")
        self.pos_y = tk.StringVar(value="0")
        self.pos_w = tk.StringVar(value="900")
        self.pos_h = tk.StringVar(value="700")
        self.app_filter.trace_add("write", lambda *_: self.refresh_apps())

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(10, 8))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="配置文件").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.config_path).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Button(top, text="选择", command=self.browse_config).grid(row=0, column=2, padx=2)
        ttk.Button(top, text="重新加载", command=self.reload).grid(row=0, column=3, padx=2)
        ttk.Button(top, text="保存配置", command=self.save).grid(row=0, column=4, padx=2)
        ttk.Button(top, text="打开目录", command=self.open_config_folder).grid(row=0, column=5, padx=2)
        ttk.Button(top, text="桌面快捷方式", command=self.create_desktop_shortcut).grid(row=0, column=6, padx=2)

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.grid(row=1, column=0, sticky="nsew", padx=10)

        left = ttk.Frame(pane)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        pane.add(left, weight=1)

        self.ws_tree = ttk.Treeview(left, columns=("name", "apps", "id"), show="headings", selectmode="browse")
        self.ws_tree.heading("name", text="启动区")
        self.ws_tree.heading("apps", text="数量")
        self.ws_tree.heading("id", text="ID")
        self.ws_tree.column("name", width=190, anchor="w")
        self.ws_tree.column("apps", width=55, anchor="center")
        self.ws_tree.column("id", width=260, anchor="w")
        self.ws_tree.grid(row=0, column=0, sticky="nsew")
        self.ws_tree.bind("<<TreeviewSelect>>", self.on_workspace_select)

        ws_buttons = ttk.Frame(left)
        ws_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for i in range(5):
            ws_buttons.columnconfigure(i, weight=1)
        ttk.Button(ws_buttons, text="新增", command=self.add_workspace).grid(row=0, column=0, padx=2, sticky="ew")
        ttk.Button(ws_buttons, text="复制", command=self.duplicate_workspace).grid(row=0, column=1, padx=2, sticky="ew")
        ttk.Button(ws_buttons, text="删除", command=self.delete_workspace).grid(row=0, column=2, padx=2, sticky="ew")
        ttk.Button(ws_buttons, text="启动", command=self.launch_workspace).grid(row=0, column=3, padx=2, sticky="ew")
        ttk.Button(ws_buttons, text="修复无反应", command=self.fix_stuck_launcher).grid(row=0, column=4, padx=2, sticky="ew")

        right = ttk.Frame(pane)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        pane.add(right, weight=4)

        ws_form = ttk.LabelFrame(right, text="启动区", padding=8)
        ws_form.grid(row=0, column=0, sticky="ew")
        ws_form.columnconfigure(1, weight=1)
        ttk.Label(ws_form, text="名称").grid(row=0, column=0, sticky="w")
        ttk.Entry(ws_form, textvariable=self.ws_name).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Checkbutton(ws_form, text="需要桌面快捷方式", variable=self.ws_shortcut).grid(row=0, column=2, padx=6)
        ttk.Checkbutton(ws_form, text="移动已有窗口", variable=self.ws_move_existing).grid(row=0, column=3, padx=6)
        ttk.Button(ws_form, text="应用启动区", command=self.apply_workspace).grid(row=0, column=4, padx=2)

        app_buttons = ttk.Frame(right)
        app_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        for i in range(10):
            app_buttons.columnconfigure(i, weight=1)
        ttk.Label(app_buttons, text="搜索").grid(row=0, column=0, padx=2, sticky="w")
        ttk.Entry(app_buttons, textvariable=self.app_filter).grid(row=0, column=1, columnspan=3, padx=2, sticky="ew")
        ttk.Checkbutton(app_buttons, text="只看失效路径", variable=self.show_missing_only, command=self.refresh_apps).grid(
            row=0, column=4, padx=2, sticky="w"
        )
        ttk.Button(app_buttons, text="校验路径", command=self.validate_paths).grid(row=0, column=5, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="备份/恢复", command=self.show_backup_manager).grid(row=0, column=6, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="批量 pythonw", command=self.fix_all_pythonw).grid(row=0, column=7, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="静默模板", command=self.make_hidden_template).grid(row=0, column=8, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="清空搜索", command=self.clear_filter).grid(row=0, column=9, padx=2, sticky="ew")

        ttk.Button(app_buttons, text="新增应用", command=self.add_app).grid(row=1, column=0, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="复制应用", command=self.duplicate_app).grid(row=1, column=1, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="应用修改", command=self.update_app).grid(row=1, column=2, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="删除应用", command=self.delete_app).grid(row=1, column=3, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="上移", command=lambda: self.move_app(-1)).grid(row=1, column=4, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="下移", command=lambda: self.move_app(1)).grid(row=1, column=5, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="启动应用", command=self.launch_app).grid(row=1, column=6, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="打开目录", command=self.open_app_folder).grid(row=1, column=7, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="改成 pythonw", command=self.fix_pythonw).grid(row=1, column=8, padx=2, pady=(5, 0), sticky="ew")
        ttk.Button(app_buttons, text="终端模板", command=self.make_terminal_template).grid(row=1, column=9, padx=2, pady=(5, 0), sticky="ew")

        self.app_tree = ttk.Treeview(
            right,
            columns=("application", "title", "path", "args", "elevated"),
            show="headings",
            selectmode="browse",
        )
        for col, text, width in (
            ("application", "应用名", 130),
            ("title", "窗口标题", 180),
            ("path", "程序路径", 330),
            ("args", "启动参数", 330),
            ("elevated", "管理员", 70),
        ):
            self.app_tree.heading(col, text=text)
            self.app_tree.column(col, width=width, anchor="w")
        self.app_tree.grid(row=2, column=0, sticky="nsew")
        self.app_tree.bind("<<TreeviewSelect>>", self.on_app_select)

        form = ttk.LabelFrame(right, text="当前应用", padding=8)
        form.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for i in range(6):
            form.columnconfigure(i, weight=1 if i in {1, 3, 5} else 0)

        ttk.Label(form, text="应用名").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.app_application).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Label(form, text="标题").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.app_title).grid(row=0, column=3, padx=6, sticky="ew")
        ttk.Label(form, text="显示器").grid(row=0, column=4, sticky="w")
        ttk.Entry(form, textvariable=self.app_monitor, width=8).grid(row=0, column=5, padx=6, sticky="w")

        ttk.Label(form, text="路径").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.app_path).grid(row=1, column=1, columnspan=4, padx=6, pady=(6, 0), sticky="ew")
        ttk.Button(form, text="选择", command=self.browse_app).grid(row=1, column=5, pady=(6, 0), sticky="ew")

        ttk.Label(form, text="参数").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.app_args).grid(row=2, column=1, columnspan=5, padx=6, pady=(6, 0), sticky="ew")

        checks = ttk.Frame(form)
        checks.grid(row=3, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(checks, text="管理员启动", variable=self.app_elevated).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(checks, text="允许提权", variable=self.app_can_elevate).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(checks, text="最小化", variable=self.app_minimized).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(checks, text="最大化", variable=self.app_maximized).pack(side=tk.LEFT, padx=(0, 16))

        pos = ttk.Frame(form)
        pos.grid(row=4, column=0, columnspan=6, sticky="w", pady=(6, 0))
        for label, var in (("X", self.pos_x), ("Y", self.pos_y), ("W", self.pos_w), ("H", self.pos_h)):
            ttk.Label(pos, text=label).pack(side=tk.LEFT)
            ttk.Entry(pos, textvariable=var, width=8).pack(side=tk.LEFT, padx=(3, 12))

        status = ttk.Label(self, textvariable=self.status, anchor="w", padding=(10, 6))
        status.grid(row=2, column=0, sticky="ew")

    def selected_workspace(self) -> dict | None:
        if self.current_workspace_index is None:
            return None
        if 0 <= self.current_workspace_index < len(self.store.workspaces):
            return self.store.workspaces[self.current_workspace_index]
        return None

    def selected_app(self) -> dict | None:
        ws = self.selected_workspace()
        if not ws or self.current_app_index is None:
            return None
        apps = ws.setdefault("applications", [])
        if 0 <= self.current_app_index < len(apps):
            return apps[self.current_app_index]
        return None

    def browse_config(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 workspaces.json",
            filetypes=[("JSON", "*.json"), ("所有文件", "*.*")],
            initialdir=str(default_config_path().parent),
        )
        if path:
            self.config_path.set(path)
            self.reload()

    def browse_app(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 exe 或脚本",
            filetypes=[("可执行文件或脚本", "*.exe *.py *.bat *.cmd"), ("所有文件", "*.*")],
        )
        if path:
            self.app_path.set(path)
            if not self.app_application.get().strip():
                self.app_application.set(Path(path).stem)

    def open_config_folder(self) -> None:
        path = Path(self.config_path.get()).expanduser()
        folder = path.parent
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    def create_desktop_shortcut(self) -> None:
        if os.name != "nt":
            messagebox.showinfo(APP_TITLE, "只有 Windows 支持创建桌面快捷方式。")
            return
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
        shortcut_path = desktop / "powertoyscheck.lnk"
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not pythonw.exists():
            pythonw = Path(sys.executable)
        script = Path(__file__).with_suffix(".pyw")

        ps = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{str(shortcut_path).replace("'", "''")}')
$shortcut.TargetPath = '{str(pythonw).replace("'", "''")}'
$shortcut.Arguments = '"{str(script).replace("'", "''")}"'
$shortcut.WorkingDirectory = '{str(script.parent).replace("'", "''")}'
$shortcut.IconLocation = '{str(pythonw).replace("'", "''")}'
$shortcut.Save()
"""
        encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                check=True,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"创建快捷方式失败：\n{exc}")
            return
        self.status.set(f"已创建桌面快捷方式：{shortcut_path}")
        messagebox.showinfo(APP_TITLE, f"已创建桌面快捷方式：\n{shortcut_path}")

    def reload(self) -> None:
        self.store = WorkspaceStore(Path(self.config_path.get()).expanduser())
        try:
            self.store.load()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"读取 JSON 失败：\n{exc}")
            return
        self.current_workspace_index = None
        self.current_app_index = None
        self.refresh_workspaces()
        if self.store.workspaces:
            self.ws_tree.selection_set("0")
            self.ws_tree.focus("0")
            self.on_workspace_select()
        self.status.set(f"已加载：{self.store.path}")

    def save(self) -> None:
        if not self.apply_current_forms_to_memory():
            return
        ws_idx = self.current_workspace_index
        app_idx = self.current_app_index
        try:
            backup = self.store.save()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"保存 JSON 失败：\n{exc}")
            return
        self.refresh_workspaces()
        self.restore_selection(ws_idx, app_idx)
        self.status.set(f"已保存。备份：{backup}")
        messagebox.showinfo(APP_TITLE, f"已保存配置。\n自动备份文件：\n{backup}")

    def restore_selection(self, ws_idx: int | None, app_idx: int | None = None) -> None:
        if ws_idx is None or not (0 <= ws_idx < len(self.store.workspaces)):
            return
        self.current_workspace_index = ws_idx
        self.ws_tree.selection_set(str(ws_idx))
        self.ws_tree.focus(str(ws_idx))
        self.refresh_apps()
        apps = self.store.workspaces[ws_idx].get("applications", [])
        if app_idx is not None and 0 <= app_idx < len(apps):
            item = str(app_idx)
            if item in self.app_tree.get_children():
                self.current_app_index = app_idx
                self.app_tree.selection_set(item)
                self.app_tree.focus(item)
                self.on_app_select()

    def apply_current_forms_to_memory(self) -> bool:
        ws = self.selected_workspace()
        if not ws:
            return True

        ws["name"] = self.ws_name.get().strip()
        ws["is-shortcut-needed"] = bool(self.ws_shortcut.get())
        ws["move-existing-windows"] = bool(self.ws_move_existing.get())

        if self.current_app_index is None:
            return True

        apps = ws.setdefault("applications", [])
        if not (0 <= self.current_app_index < len(apps)):
            return True

        if not self.app_path.get().strip():
            return messagebox.askyesno(APP_TITLE, "当前应用路径为空，确定仍然保存吗？")

        apps[self.current_app_index] = self.form_to_app(apps[self.current_app_index])
        return True

    def refresh_workspaces(self) -> None:
        self.ws_tree.delete(*self.ws_tree.get_children())
        for i, ws in enumerate(self.store.workspaces):
            self.ws_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(ws.get("name", ""), len(ws.get("applications", [])), ws.get("id", "")),
            )
        self.refresh_apps()

    def refresh_apps(self) -> None:
        self.app_tree.delete(*self.app_tree.get_children())
        ws = self.selected_workspace()
        if not ws:
            self.clear_workspace_form()
            self.clear_app_form()
            return
        self.ws_name.set(ws.get("name", ""))
        self.ws_shortcut.set(bool(ws.get("is-shortcut-needed", False)))
        self.ws_move_existing.set(bool(ws.get("move-existing-windows", False)))
        for i, app in enumerate(ws.setdefault("applications", [])):
            if not self.app_visible(app):
                continue
            self.app_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    app.get("application", ""),
                    app.get("title", ""),
                    app.get("application-path", ""),
                    app.get("command-line-arguments", ""),
                    "是" if app.get("is-elevated") else "否",
                ),
            )
        self.clear_app_form()

    def app_visible(self, app: dict) -> bool:
        needle = self.app_filter.get().strip().lower()
        if needle:
            haystack = " ".join(
                str(app.get(key, ""))
                for key in ("application", "title", "application-path", "command-line-arguments")
            ).lower()
            if needle not in haystack:
                return False
        if self.show_missing_only.get() and not app_path_missing(app):
            return False
        return True

    def clear_filter(self) -> None:
        self.app_filter.set("")
        self.show_missing_only.set(False)
        self.refresh_apps()

    def clear_workspace_form(self) -> None:
        self.ws_name.set("")
        self.ws_shortcut.set(False)
        self.ws_move_existing.set(False)

    def clear_app_form(self) -> None:
        self.current_app_index = None
        self.app_application.set("")
        self.app_title.set("")
        self.app_path.set("")
        self.app_args.set("")
        self.app_elevated.set(False)
        self.app_can_elevate.set(False)
        self.app_minimized.set(False)
        self.app_maximized.set(False)
        self.app_monitor.set("1")
        self.pos_x.set("0")
        self.pos_y.set("0")
        self.pos_w.set("900")
        self.pos_h.set("700")

    def on_workspace_select(self, _event=None) -> None:
        sel = self.ws_tree.selection()
        if not sel:
            return
        if self.current_workspace_index is not None and self.current_app_index is not None:
            self.apply_current_forms_to_memory()
        self.current_workspace_index = int(sel[0])
        self.current_app_index = None
        self.refresh_apps()

    def on_app_select(self, _event=None) -> None:
        sel = self.app_tree.selection()
        if not sel:
            return
        if self.current_app_index is not None and self.current_app_index != int(sel[0]):
            self.apply_current_forms_to_memory()
        self.current_app_index = int(sel[0])
        app = self.selected_app()
        if not app:
            return
        pos = app.get("position") or {}
        self.app_application.set(app.get("application", ""))
        self.app_title.set(app.get("title", ""))
        self.app_path.set(app.get("application-path", ""))
        self.app_args.set(app.get("command-line-arguments", ""))
        self.app_elevated.set(bool(app.get("is-elevated", False)))
        self.app_can_elevate.set(bool(app.get("can-launch-elevated", False)))
        self.app_minimized.set(bool(app.get("minimized", False)))
        self.app_maximized.set(bool(app.get("maximized", False)))
        self.app_monitor.set(str(app.get("monitor", 1)))
        self.pos_x.set(str(pos.get("X", 0)))
        self.pos_y.set(str(pos.get("Y", 0)))
        self.pos_w.set(str(pos.get("width", 900)))
        self.pos_h.set(str(pos.get("height", 700)))

    def add_workspace(self) -> None:
        name = simpledialog.askstring(APP_TITLE, "启动区名称：", initialvalue="新启动区")
        if not name:
            return
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.store.workspaces.append(
            {
                "id": new_guid(),
                "name": name,
                "applications": [],
                "is-shortcut-needed": True,
                "move-existing-windows": True,
                "creation-time": now,
                "last-launched-time": "",
                "monitor-configuration": "",
            }
        )
        self.refresh_workspaces()
        idx = len(self.store.workspaces) - 1
        self.ws_tree.selection_set(str(idx))
        self.ws_tree.focus(str(idx))
        self.on_workspace_select()

    def duplicate_workspace(self) -> None:
        ws = self.selected_workspace()
        if not ws:
            return
        clone = deepcopy(ws)
        clone["id"] = new_guid()
        clone["name"] = f"{clone.get('name', '启动区')} 副本"
        for app in clone.get("applications", []):
            app["id"] = new_guid()
        self.store.workspaces.append(clone)
        self.refresh_workspaces()

    def delete_workspace(self) -> None:
        if self.current_workspace_index is None:
            return
        ws = self.selected_workspace()
        if not ws:
            return
        if not messagebox.askyesno(APP_TITLE, f"确定删除启动区“{ws.get('name', '')}”吗？"):
            return
        del self.store.workspaces[self.current_workspace_index]
        self.current_workspace_index = None
        self.refresh_workspaces()

    def apply_workspace(self) -> None:
        ws = self.selected_workspace()
        if not ws:
            return
        ws["name"] = self.ws_name.get().strip()
        ws["is-shortcut-needed"] = bool(self.ws_shortcut.get())
        ws["move-existing-windows"] = bool(self.ws_move_existing.get())
        self.refresh_workspaces()
        self.status.set("启动区修改已应用到内存。点击“保存配置”写入文件。")

    def read_int(self, var: tk.StringVar, default: int) -> int:
        try:
            return int(var.get().strip())
        except ValueError:
            return default

    def form_to_app(self, existing: dict | None = None) -> dict:
        app = deepcopy(existing) if existing else {}
        app.setdefault("id", new_guid())
        app["application"] = self.app_application.get().strip() or Path(self.app_path.get()).stem
        app["application-path"] = self.app_path.get().strip()
        app["title"] = self.app_title.get().strip()
        app.setdefault("package-full-name", "")
        app.setdefault("app-user-model-id", "")
        app.setdefault("pwa-app-id", "")
        app["command-line-arguments"] = self.app_args.get()
        app["is-elevated"] = bool(self.app_elevated.get())
        app["can-launch-elevated"] = bool(self.app_can_elevate.get())
        app["minimized"] = bool(self.app_minimized.get())
        app["maximized"] = bool(self.app_maximized.get())
        app["position"] = {
            "X": self.read_int(self.pos_x, 0),
            "Y": self.read_int(self.pos_y, 0),
            "width": max(1, self.read_int(self.pos_w, 900)),
            "height": max(1, self.read_int(self.pos_h, 700)),
        }
        app["monitor"] = self.read_int(self.app_monitor, 1)
        app.setdefault("version", "1")
        return app

    def add_app(self) -> None:
        ws = self.selected_workspace()
        if not ws:
            messagebox.showwarning(APP_TITLE, "请先选择或新增一个启动区。")
            return
        app = self.form_to_app()
        if not app.get("application-path"):
            messagebox.showwarning(APP_TITLE, "应用路径不能为空。")
            return
        ws.setdefault("applications", []).append(app)
        idx = len(ws["applications"]) - 1
        self.refresh_workspaces()
        self.restore_selection(self.current_workspace_index, idx)

    def update_app(self) -> None:
        ws = self.selected_workspace()
        if not ws or self.current_app_index is None:
            return
        apps = ws.setdefault("applications", [])
        apps[self.current_app_index] = self.form_to_app(apps[self.current_app_index])
        idx = self.current_app_index
        self.refresh_workspaces()
        self.restore_selection(self.current_workspace_index, idx)
        self.status.set("应用修改已应用到内存。点击“保存配置”写入文件。")

    def delete_app(self) -> None:
        ws = self.selected_workspace()
        app = self.selected_app()
        if not ws or app is None or self.current_app_index is None:
            return
        label = app.get("application") or app.get("application-path") or "selected app"
        if not messagebox.askyesno(APP_TITLE, f"确定删除“{label}”吗？"):
            return
        del ws.setdefault("applications", [])[self.current_app_index]
        self.current_app_index = None
        self.refresh_workspaces()
        self.ws_tree.selection_set(str(self.current_workspace_index))
        self.refresh_apps()

    def duplicate_app(self) -> None:
        ws = self.selected_workspace()
        app = self.selected_app()
        if not ws or app is None:
            messagebox.showwarning(APP_TITLE, "请先选择一个应用。")
            return
        clone = deepcopy(app)
        clone["id"] = new_guid()
        clone["application"] = f"{clone.get('application', '应用')} 副本"
        apps = ws.setdefault("applications", [])
        insert_at = (self.current_app_index or 0) + 1
        apps.insert(insert_at, clone)
        self.refresh_workspaces()
        self.restore_selection(self.current_workspace_index, insert_at)
        self.status.set("已复制应用。点击“保存配置”写入文件。")

    def move_app(self, delta: int) -> None:
        ws = self.selected_workspace()
        if not ws or self.current_app_index is None:
            return
        apps = ws.setdefault("applications", [])
        old = self.current_app_index
        new = old + delta
        if not (0 <= new < len(apps)):
            return
        apps[old], apps[new] = apps[new], apps[old]
        self.current_app_index = new
        self.refresh_apps()
        self.restore_selection(self.current_workspace_index, new)

    def open_app_folder(self) -> None:
        path = self.app_path.get().strip()
        if not path:
            app = self.selected_app()
            path = app.get("application-path", "") if app else ""
        if not path:
            messagebox.showwarning(APP_TITLE, "当前应用路径为空。")
            return
        folder = expanded_path(path).parent
        if not folder.exists():
            messagebox.showwarning(APP_TITLE, f"目录不存在：\n{folder}")
            return
        os.startfile(str(folder))

    def validate_paths(self) -> None:
        missing: list[str] = []
        total = 0
        for ws in self.store.workspaces:
            for app in ws.get("applications", []):
                total += 1
                if app_path_missing(app):
                    label = app.get("application") or app.get("title") or "未命名应用"
                    missing.append(f"[{ws.get('name', '启动区')}] {label}: {app.get('application-path', '')}")

        if not missing:
            self.status.set(f"路径校验通过：{total} 个应用。")
            messagebox.showinfo(APP_TITLE, f"路径校验通过。\n共检查 {total} 个应用。")
            return

        self.show_missing_only.set(True)
        self.refresh_apps()
        preview = "\n".join(missing[:20])
        more = "" if len(missing) <= 20 else f"\n\n还有 {len(missing) - 20} 个未显示。"
        self.status.set(f"发现 {len(missing)} 个失效路径。已切换到“只看失效路径”。")
        messagebox.showwarning(APP_TITLE, f"发现 {len(missing)} 个失效路径：\n\n{preview}{more}")

    def fix_all_pythonw(self) -> None:
        changed = 0
        for ws in self.store.workspaces:
            for app in ws.get("applications", []):
                path = app.get("application-path", "")
                if Path(path).name.lower() == "python.exe":
                    new_path = pythonw_path(path)
                    if expanded_path(new_path).exists():
                        app["application-path"] = new_path
                        changed += 1

        if changed:
            self.refresh_apps()
            self.status.set(f"已批量改成 pythonw.exe：{changed} 项。点击“保存配置”写入文件。")
            messagebox.showinfo(APP_TITLE, f"已修改 {changed} 个 python.exe 项。\n点击“保存配置”写入文件。")
        else:
            messagebox.showinfo(APP_TITLE, "没有找到可修改的 python.exe 项，或对应 pythonw.exe 不存在。")

    def show_backup_manager(self) -> None:
        win = tk.Toplevel(self)
        win.title("备份/恢复")
        win.geometry("760x420")
        win.minsize(640, 360)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)

        backup_dir = self.store.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        backups = sorted(backup_dir.glob("workspaces-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

        listbox = tk.Listbox(win)
        listbox.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=10, pady=(10, 6))
        for backup in backups:
            stamp = datetime.fromtimestamp(backup.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            listbox.insert(tk.END, f"{stamp}    {backup.name}")

        def selected_backup() -> Path | None:
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning(APP_TITLE, "请先选择一个备份。", parent=win)
                return None
            return backups[sel[0]]

        def restore() -> None:
            backup = selected_backup()
            if not backup:
                return
            if not messagebox.askyesno(APP_TITLE, f"确定恢复这个备份吗？\n\n{backup}", parent=win):
                return
            self.store.backup()
            shutil.copy2(backup, self.store.path)
            win.destroy()
            self.reload()
            self.status.set(f"已恢复备份：{backup}")

        def delete_backup() -> None:
            backup = selected_backup()
            if not backup:
                return
            if not messagebox.askyesno(APP_TITLE, f"确定删除这个备份吗？\n\n{backup}", parent=win):
                return
            backup.unlink()
            index = listbox.curselection()[0]
            listbox.delete(index)
            backups.pop(index)

        ttk.Button(win, text="恢复选中备份", command=restore).grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        ttk.Button(win, text="删除选中备份", command=delete_backup).grid(row=1, column=1, padx=4, pady=(0, 10), sticky="ew")
        ttk.Button(win, text="打开备份目录", command=lambda: os.startfile(str(backup_dir))).grid(
            row=1, column=2, padx=4, pady=(0, 10), sticky="ew"
        )
        ttk.Button(win, text="立即备份当前配置", command=lambda: messagebox.showinfo(APP_TITLE, f"已备份：\n{self.store.backup()}", parent=win)).grid(
            row=1, column=3, padx=4, pady=(0, 10), sticky="ew"
        )
        ttk.Button(win, text="关闭", command=win.destroy).grid(row=1, column=4, padx=10, pady=(0, 10), sticky="ew")

    def fix_pythonw(self) -> None:
        app = self.selected_app()
        if not app:
            path = self.app_path.get()
            if is_python_path(path):
                self.app_path.set(pythonw_path(path))
            return
        path = app.get("application-path", "")
        if not is_python_path(path):
            messagebox.showinfo(APP_TITLE, "当前应用不是 python.exe/pythonw.exe。")
            return
        new_path = pythonw_path(path)
        app["application-path"] = new_path
        self.app_path.set(new_path)
        self.refresh_apps()
        self.status.set("已在内存中改成 pythonw.exe。点击“保存配置”写入文件。")

    def make_terminal_template(self) -> None:
        exe = filedialog.askopenfilename(
            title="选择要在 Windows Terminal 中启动的 exe",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if not exe:
            return
        title = Path(exe).stem
        wt = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "wt.exe"
        self.app_application.set("Windows Terminal")
        self.app_title.set(title)
        self.app_path.set(str(wt))
        self.app_args.set(f'new-tab --title "{title}" -d "{Path(exe).parent}" cmd /k ".\\{Path(exe).name}"')

    def make_hidden_template(self) -> None:
        exe = filedialog.askopenfilename(
            title="选择要静默后台启动的 exe",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if not exe:
            return
        exe_path = Path(exe)
        ps = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        self.app_application.set(f"{exe_path.stem} 后台启动")
        self.app_title.set(exe_path.stem)
        self.app_path.set(str(ps))
        self.app_args.set(
            "-NoProfile -WindowStyle Hidden -Command "
            f"\"Start-Process -FilePath '{ps_single(str(exe_path))}' -WorkingDirectory '{ps_single(str(exe_path.parent))}'\""
        )

    def fix_stuck_launcher(self, show_message: bool = True) -> int:
        names = {
            "PowerToys.WorkspacesLauncher",
            "PowerToys.WorkspacesLauncherUI",
            "PowerToys.WorkspacesWindowArranger",
        }
        killed = 0
        for proc in subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Get-Process PowerToys.WorkspacesLauncher,PowerToys.WorkspacesLauncherUI,PowerToys.WorkspacesWindowArranger "
                "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id",
            ],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        ).stdout.splitlines():
            proc = proc.strip()
            if not proc.isdigit():
                continue
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", f"Stop-Process -Id {proc} -Force"],
                    check=False,
                    creationflags=CREATE_NO_WINDOW,
                )
                killed += 1
            except Exception:
                pass

        if show_message:
            if killed:
                self.status.set(f"已清理卡住的 PowerToys Workspaces 启动器进程：{killed} 个。")
                messagebox.showinfo(APP_TITLE, f"已清理卡住的启动器进程：{killed} 个。\n现在可以再点桌面“快速启动”。")
            else:
                self.status.set("没有发现卡住的 Workspaces 启动器进程。")
                messagebox.showinfo(APP_TITLE, "没有发现卡住的 Workspaces 启动器进程。")
        return killed

    def launch_workspace(self) -> None:
        ws = self.selected_workspace()
        if not ws:
            return
        self.fix_stuck_launcher(show_message=False)
        launcher = default_launcher_path()
        if not launcher.exists():
            path = filedialog.askopenfilename(title="选择 PowerToys.WorkspacesLauncher.exe")
            if not path:
                return
            launcher = Path(path)
        try:
            subprocess.Popen(
                [str(launcher), ws.get("id", ""), "1"],
                cwd=str(launcher.parent),
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"启动启动区失败：\n{exc}")

    def launch_app(self) -> None:
        app = self.selected_app() or self.form_to_app()
        path = app.get("application-path", "")
        if not path:
            return
        try:
            args = (app.get("command-line-arguments", "") or "").strip()
            command_line = subprocess.list2cmdline([path])
            if args:
                command_line = f"{command_line} {args}"
            subprocess.Popen(command_line, cwd=str(Path(path).parent), creationflags=CREATE_NO_WINDOW)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"启动应用失败：\n{exc}")


if __name__ == "__main__":
    PowerToysCheck().mainloop()
