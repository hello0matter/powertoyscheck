# powertoyscheck

`powertoyscheck` 是一个用 Python/Tkinter 写的 PowerToys Workspaces 配置管理工具。

它直接编辑这个文件：

```text
%LOCALAPPDATA%\Microsoft\PowerToys\Workspaces\workspaces.json
```

本机通常是：

```text
C:\Users\Administrator\AppData\Local\Microsoft\PowerToys\Workspaces\workspaces.json
```

官方文档：

```text
https://learn.microsoft.com/en-us/windows/powertoys/workspaces
```

## 启动

不需要安装第三方 Python 包。

带控制台调试：

```powershell
python .\powertoyscheck.py
```

无黑窗口启动：

```powershell
pythonw .\powertoyscheck.pyw
```

也可以直接双击：

```text
powertoyscheck.pyw
```

程序里有“桌面快捷方式”按钮，可以在桌面生成 `powertoyscheck.lnk`。

## 重要交互

修改下面“当前应用”里的路径、参数、管理员启动等字段后，直接点顶部“保存配置”即可。

`保存配置` 会自动先把当前表单内容应用到选中的启动区和应用，再写入 JSON 文件。

如果只想暂存但不保存文件，可以点“应用修改”。

## 功能

- 读取和保存 PowerToys Workspaces 的 `workspaces.json`。
- 每次保存前自动备份。
- 启动区新增、复制、删除、重命名。
- 应用新增、修改、删除、上移、下移、启动。
- 应用搜索过滤，支持按应用名、标题、路径、参数搜索。
- “只看失效路径”和“校验路径”，快速找出路径为空或文件不存在的启动项。
- 复制应用、打开应用所在目录。
- 修改应用路径、启动参数、管理员启动、最小化、最大化、显示器和窗口位置。
- 调用 PowerToys 自带 `PowerToys.WorkspacesLauncher.exe` 启动整个启动区。
- 一键把 `python.exe` 改成 `pythonw.exe`，避免 GUI Python 脚本出现黑窗口。
- 批量把所有可修复的 `python.exe` 改成 `pythonw.exe`。
- 生成 Windows Terminal 启动 exe 的参数模板。
- 生成 PowerShell 静默后台启动 exe 的参数模板。
- 备份/恢复窗口：查看、恢复、删除备份，也可以立即备份当前配置。

## 常用按钮

- `保存配置`：自动应用当前正在编辑的启动区/应用表单，然后写入 JSON。
- `应用修改`：只把当前应用表单应用到内存，不写文件。
- `校验路径`：扫描所有启动区应用，发现失效路径后自动切到“只看失效路径”。
- `备份/恢复`：管理自动备份，恢复前会先备份当前配置。
- `批量 pythonw`：把存在对应 `pythonw.exe` 的 `python.exe` 项批量修好。
- `终端模板`：生成 `wt.exe ... cmd /k ...`，适合要看控制台输出的 exe。
- `静默模板`：生成 `powershell.exe -WindowStyle Hidden ... Start-Process`，适合后台启动 exe。

## Python 黑窗口

GUI Python 脚本建议用 `pythonw.exe`，不要用 `python.exe`。

示例：

```json
{
  "application-path": "D:\\Program Files\\Python\\Python311\\pythonw.exe",
  "command-line-arguments": "\"D:\\tmp\\anjian\\pj\\st\\tmp\\claudecodexsessionkill\\session_cleaner_gui.py\""
}
```

`pythonw.exe` 不创建控制台窗口，所以不会因为关闭黑窗口而把 GUI 脚本关掉。

## Windows Terminal 启动 exe

路径填：

```text
C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\wt.exe
```

参数示例：

```text
new-tab --title "CLI Proxy API" cmd /k "D:\tmp\anjian\pj\st\CLIProxyAPI_7.2.27_windows_amd64\cli-proxy-api.exe"
```

如果你想后台静默启动 exe，不要用 Windows Terminal，应该改用 `Start-Process` 或单独的启动器。

## 备份位置

保存前的备份在：

```text
%LOCALAPPDATA%\Microsoft\PowerToys\Workspaces\powertoyscheck-backups\
```

## 注意

- 程序会保留 PowerToys JSON 里不认识的字段。
- 如果 PowerToys 正在运行，保存后它不一定立刻重新读取配置；必要时重启 PowerToys。
