import json
import os
import subprocess
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_TITLE = "PowerToys Workspaces Check"
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
        backup_dir = self.path.parent / "powertoyscheck-backups"
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
        self.status = tk.StringVar(value="Ready")

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
        self.pos_x = tk.StringVar(value="0")
        self.pos_y = tk.StringVar(value="0")
        self.pos_w = tk.StringVar(value="900")
        self.pos_h = tk.StringVar(value="700")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(10, 8))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Config").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.config_path).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Button(top, text="Browse", command=self.browse_config).grid(row=0, column=2, padx=2)
        ttk.Button(top, text="Reload", command=self.reload).grid(row=0, column=3, padx=2)
        ttk.Button(top, text="Save", command=self.save).grid(row=0, column=4, padx=2)
        ttk.Button(top, text="Open Folder", command=self.open_config_folder).grid(row=0, column=5, padx=2)

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.grid(row=1, column=0, sticky="nsew", padx=10)

        left = ttk.Frame(pane)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        pane.add(left, weight=1)

        self.ws_tree = ttk.Treeview(left, columns=("name", "apps", "id"), show="headings", selectmode="browse")
        self.ws_tree.heading("name", text="Workspace")
        self.ws_tree.heading("apps", text="Apps")
        self.ws_tree.heading("id", text="ID")
        self.ws_tree.column("name", width=190, anchor="w")
        self.ws_tree.column("apps", width=55, anchor="center")
        self.ws_tree.column("id", width=260, anchor="w")
        self.ws_tree.grid(row=0, column=0, sticky="nsew")
        self.ws_tree.bind("<<TreeviewSelect>>", self.on_workspace_select)

        ws_buttons = ttk.Frame(left)
        ws_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for i in range(4):
            ws_buttons.columnconfigure(i, weight=1)
        ttk.Button(ws_buttons, text="Add", command=self.add_workspace).grid(row=0, column=0, padx=2, sticky="ew")
        ttk.Button(ws_buttons, text="Duplicate", command=self.duplicate_workspace).grid(row=0, column=1, padx=2, sticky="ew")
        ttk.Button(ws_buttons, text="Delete", command=self.delete_workspace).grid(row=0, column=2, padx=2, sticky="ew")
        ttk.Button(ws_buttons, text="Launch", command=self.launch_workspace).grid(row=0, column=3, padx=2, sticky="ew")

        right = ttk.Frame(pane)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        pane.add(right, weight=4)

        ws_form = ttk.LabelFrame(right, text="Workspace", padding=8)
        ws_form.grid(row=0, column=0, sticky="ew")
        ws_form.columnconfigure(1, weight=1)
        ttk.Label(ws_form, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(ws_form, textvariable=self.ws_name).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Checkbutton(ws_form, text="Desktop shortcut needed", variable=self.ws_shortcut).grid(row=0, column=2, padx=6)
        ttk.Checkbutton(ws_form, text="Move existing windows", variable=self.ws_move_existing).grid(row=0, column=3, padx=6)
        ttk.Button(ws_form, text="Apply Workspace", command=self.apply_workspace).grid(row=0, column=4, padx=2)

        app_buttons = ttk.Frame(right)
        app_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        for i in range(8):
            app_buttons.columnconfigure(i, weight=1)
        ttk.Button(app_buttons, text="Add App", command=self.add_app).grid(row=0, column=0, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="Update App", command=self.update_app).grid(row=0, column=1, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="Delete App", command=self.delete_app).grid(row=0, column=2, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="Up", command=lambda: self.move_app(-1)).grid(row=0, column=3, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="Down", command=lambda: self.move_app(1)).grid(row=0, column=4, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="Launch App", command=self.launch_app).grid(row=0, column=5, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="Python -> pythonw", command=self.fix_pythonw).grid(row=0, column=6, padx=2, sticky="ew")
        ttk.Button(app_buttons, text="WT Template", command=self.make_terminal_template).grid(row=0, column=7, padx=2, sticky="ew")

        self.app_tree = ttk.Treeview(
            right,
            columns=("application", "title", "path", "args", "elevated"),
            show="headings",
            selectmode="browse",
        )
        for col, text, width in (
            ("application", "Application", 130),
            ("title", "Window Title", 180),
            ("path", "Path", 330),
            ("args", "Arguments", 330),
            ("elevated", "Admin", 70),
        ):
            self.app_tree.heading(col, text=text)
            self.app_tree.column(col, width=width, anchor="w")
        self.app_tree.grid(row=2, column=0, sticky="nsew")
        self.app_tree.bind("<<TreeviewSelect>>", self.on_app_select)

        form = ttk.LabelFrame(right, text="Selected Application", padding=8)
        form.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for i in range(6):
            form.columnconfigure(i, weight=1 if i in {1, 3, 5} else 0)

        ttk.Label(form, text="Application").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.app_application).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Label(form, text="Title").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.app_title).grid(row=0, column=3, padx=6, sticky="ew")
        ttk.Label(form, text="Monitor").grid(row=0, column=4, sticky="w")
        ttk.Entry(form, textvariable=self.app_monitor, width=8).grid(row=0, column=5, padx=6, sticky="w")

        ttk.Label(form, text="Path").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.app_path).grid(row=1, column=1, columnspan=4, padx=6, pady=(6, 0), sticky="ew")
        ttk.Button(form, text="Browse", command=self.browse_app).grid(row=1, column=5, pady=(6, 0), sticky="ew")

        ttk.Label(form, text="Arguments").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.app_args).grid(row=2, column=1, columnspan=5, padx=6, pady=(6, 0), sticky="ew")

        checks = ttk.Frame(form)
        checks.grid(row=3, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(checks, text="Launch as Admin", variable=self.app_elevated).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(checks, text="Can Launch Elevated", variable=self.app_can_elevate).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(checks, text="Minimized", variable=self.app_minimized).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(checks, text="Maximized", variable=self.app_maximized).pack(side=tk.LEFT, padx=(0, 16))

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
            title="Select workspaces.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            initialdir=str(default_config_path().parent),
        )
        if path:
            self.config_path.set(path)
            self.reload()

    def browse_app(self) -> None:
        path = filedialog.askopenfilename(
            title="Select executable or script",
            filetypes=[("Executable or script", "*.exe *.py *.bat *.cmd"), ("All files", "*.*")],
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

    def reload(self) -> None:
        self.store = WorkspaceStore(Path(self.config_path.get()).expanduser())
        try:
            self.store.load()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Failed to load JSON:\n{exc}")
            return
        self.current_workspace_index = None
        self.current_app_index = None
        self.refresh_workspaces()
        if self.store.workspaces:
            self.ws_tree.selection_set("0")
            self.ws_tree.focus("0")
            self.on_workspace_select()
        self.status.set(f"Loaded {self.store.path}")

    def save(self) -> None:
        try:
            backup = self.store.save()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Failed to save JSON:\n{exc}")
            return
        self.status.set(f"Saved. Backup: {backup}")
        messagebox.showinfo(APP_TITLE, f"Saved.\nBackup created:\n{backup}")

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
            self.app_tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    app.get("application", ""),
                    app.get("title", ""),
                    app.get("application-path", ""),
                    app.get("command-line-arguments", ""),
                    "yes" if app.get("is-elevated") else "no",
                ),
            )
        self.clear_app_form()

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
        self.current_workspace_index = int(sel[0])
        self.current_app_index = None
        self.refresh_apps()

    def on_app_select(self, _event=None) -> None:
        sel = self.app_tree.selection()
        if not sel:
            return
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
        name = simpledialog.askstring(APP_TITLE, "Workspace name:", initialvalue="New workspace")
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
        clone["name"] = f"{clone.get('name', 'Workspace')} copy"
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
        if not messagebox.askyesno(APP_TITLE, f"Delete workspace '{ws.get('name', '')}'?"):
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
        self.status.set("Workspace updated in memory. Click Save to write file.")

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
            messagebox.showwarning(APP_TITLE, "Select or create a workspace first.")
            return
        app = self.form_to_app()
        if not app.get("application-path"):
            messagebox.showwarning(APP_TITLE, "Application path is required.")
            return
        ws.setdefault("applications", []).append(app)
        self.refresh_workspaces()
        self.ws_tree.selection_set(str(self.current_workspace_index))
        self.refresh_apps()
        idx = len(ws["applications"]) - 1
        self.app_tree.selection_set(str(idx))
        self.app_tree.focus(str(idx))
        self.on_app_select()

    def update_app(self) -> None:
        ws = self.selected_workspace()
        if not ws or self.current_app_index is None:
            return
        apps = ws.setdefault("applications", [])
        apps[self.current_app_index] = self.form_to_app(apps[self.current_app_index])
        idx = self.current_app_index
        self.refresh_workspaces()
        self.ws_tree.selection_set(str(self.current_workspace_index))
        self.refresh_apps()
        self.app_tree.selection_set(str(idx))
        self.app_tree.focus(str(idx))
        self.on_app_select()
        self.status.set("Application updated in memory. Click Save to write file.")

    def delete_app(self) -> None:
        ws = self.selected_workspace()
        app = self.selected_app()
        if not ws or app is None or self.current_app_index is None:
            return
        label = app.get("application") or app.get("application-path") or "selected app"
        if not messagebox.askyesno(APP_TITLE, f"Delete '{label}'?"):
            return
        del ws.setdefault("applications", [])[self.current_app_index]
        self.current_app_index = None
        self.refresh_workspaces()
        self.ws_tree.selection_set(str(self.current_workspace_index))
        self.refresh_apps()

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
        self.app_tree.selection_set(str(new))
        self.app_tree.focus(str(new))
        self.on_app_select()

    def fix_pythonw(self) -> None:
        app = self.selected_app()
        if not app:
            path = self.app_path.get()
            if is_python_path(path):
                self.app_path.set(pythonw_path(path))
            return
        path = app.get("application-path", "")
        if not is_python_path(path):
            messagebox.showinfo(APP_TITLE, "Selected app is not python.exe/pythonw.exe.")
            return
        new_path = pythonw_path(path)
        app["application-path"] = new_path
        self.app_path.set(new_path)
        self.refresh_apps()
        self.status.set("Changed python.exe to pythonw.exe in memory. Click Save to write file.")

    def make_terminal_template(self) -> None:
        exe = filedialog.askopenfilename(
            title="Select exe to run in Windows Terminal",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if not exe:
            return
        title = Path(exe).stem
        wt = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "wt.exe"
        self.app_application.set("Windows Terminal")
        self.app_title.set(title)
        self.app_path.set(str(wt))
        self.app_args.set(f'new-tab --title "{title}" cmd /k "{exe}"')

    def launch_workspace(self) -> None:
        ws = self.selected_workspace()
        if not ws:
            return
        launcher = default_launcher_path()
        if not launcher.exists():
            path = filedialog.askopenfilename(title="Select PowerToys.WorkspacesLauncher.exe")
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
            messagebox.showerror(APP_TITLE, f"Failed to launch workspace:\n{exc}")

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
            messagebox.showerror(APP_TITLE, f"Failed to launch app:\n{exc}")


if __name__ == "__main__":
    PowerToysCheck().mainloop()
