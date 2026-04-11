# Desktop App Workspace

This folder is the dedicated launch and packaging surface for the Sopotek Trading AI desktop application.

What lives here:

- `main.py`: desktop bootstrap entrypoint
- `Launch Sopotek Trading AI.cmd`: Windows launcher
- `scripts/launch_ui.ps1`: desktop startup helper
- `environment.yml`: Conda environment definition for the desktop app
- `requirements.txt`: forwards to the repo root requirements file
- `Dockerfile`: desktop image build file

Canonical desktop source code remains in:

- `../src`

That keeps the desktop app in one source tree while giving you a clean dedicated folder for launch, environment, and packaging files.

Common commands:

```powershell
cd desktop_app
python main.py
```

```powershell
cd desktop_app
.\Launch Sopotek Trading AI.cmd
```

```powershell
docker build -f desktop_app/Dockerfile -t sopotek-trading-ai-desktop ..
```
