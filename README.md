# powertoyscheck

`powertoyscheck` is a small Python/Tkinter GUI for directly managing Microsoft PowerToys Workspaces configuration.

It edits:

```text
%LOCALAPPDATA%\Microsoft\PowerToys\Workspaces\workspaces.json
```

On this machine that is usually:

```text
C:\Users\Administrator\AppData\Local\Microsoft\PowerToys\Workspaces\workspaces.json
```

## Why

PowerToys Workspaces supports editing apps, window positions, CLI arguments, desktop shortcuts, and "Launch as Admin". Microsoft also documents an important caveat: re-capturing a workspace can remove previous CLI arguments and settings. This tool edits the JSON directly so you can add, remove, and update workspace entries without re-capturing.

Official reference:

```text
https://learn.microsoft.com/en-us/windows/powertoys/workspaces
```

## Run

No third-party Python packages are required.

Console/debug mode:

```powershell
python .\powertoyscheck.py
```

No console window:

```powershell
pythonw .\powertoyscheck.pyw
```

You can also double-click `powertoyscheck.pyw`.

## Main Features

- Load and save `workspaces.json`.
- Automatic timestamped backup before every save.
- Add, duplicate, delete, and rename workspaces.
- Add, update, delete, reorder, and launch workspace apps.
- Edit app path, arguments, admin flag, minimized/maximized flags, monitor, and position.
- Launch the selected workspace through PowerToys' own `PowerToys.WorkspacesLauncher.exe`.
- Convert a selected `python.exe` app entry to `pythonw.exe` to avoid the black console window.
- Generate a Windows Terminal command template for launching an `.exe` inside `wt.exe`.

## Avoiding the Python Black Window

For GUI Python scripts, use `pythonw.exe` instead of `python.exe`.

Example PowerToys app entry:

```json
{
  "application-path": "D:\\Program Files\\Python\\Python311\\pythonw.exe",
  "command-line-arguments": "\"D:\\tmp\\anjian\\pj\\st\\tmp\\claudecodexsessionkill\\session_cleaner_gui.py\""
}
```

`pythonw.exe` does not create a console window, so closing a console window cannot kill the GUI script.

## Running an EXE in Windows Terminal

Use `wt.exe` as the app path and put the executable in the arguments.

Example:

```json
{
  "application-path": "C:\\Users\\Administrator\\AppData\\Local\\Microsoft\\WindowsApps\\wt.exe",
  "command-line-arguments": "new-tab --title \"CLI Proxy API\" cmd /k \"D:\\tmp\\anjian\\pj\\st\\CLIProxyAPI_7.2.27_windows_amd64\\cli-proxy-api.exe\""
}
```

If you want to run an executable silently in the background, do not use Windows Terminal. Use a small launcher or `Start-Process` instead.

## Backup Location

Backups are written next to the PowerToys file:

```text
%LOCALAPPDATA%\Microsoft\PowerToys\Workspaces\powertoyscheck-backups\
```

## Notes

- This tool preserves unknown JSON fields when editing existing records.
- Click `Save` to write changes. Editing the form only changes the in-memory copy.
- If PowerToys is open while you edit the file, reload PowerToys after saving if it does not notice the change.
