# Install rolescan on your machine

One Python entry point covers every platform: `python3 rolescan.py <command>`.
The shell names (`./setup.sh`, `./doctor.sh`, `bin/check.sh`, `bin/personas`)
are wrappers around it and exist because the docs and the gate use them.

The floor is **Python 3.12**. `rolescan setup` finds an interpreter, verifies the
version, and says what is missing.

## Linux

```bash
git clone https://github.com/jarrettdev/rolescan.git
cd rolescan
./setup.sh                 # venv, dependencies, .env, filters/active.json
./doctor.sh                # CORE_READY
bin/personas               # four test users -> data/results/*.csv, no keys
bin/check.sh               # the offline gate
```

Browser source (optional, hiring.cafe only):

```bash
./setup.sh --browser                      # adds seleniumbase
sudo apt install chromium xvfb            # or your distro's packages
xvfb-run -a python3 hc_scraper.py --dry-run
```

## macOS

```bash
git clone https://github.com/jarrettdev/rolescan.git
cd rolescan
./setup.sh
./doctor.sh
bin/personas
```

Optional browser source: install Google Chrome or Chromium; `./setup.sh --browser`
adds seleniumbase. The board poller needs no browser.

## WSL2

Use **WSL2** (Ubuntu). The same commands as Linux work inside WSL.

```powershell
wsl --install -d Ubuntu
```
```bash
# inside WSL
git clone https://github.com/jarrettdev/rolescan.git && cd rolescan
./setup.sh && ./doctor.sh && bin/personas
```

**Native Windows is untested.** The code locks files with `fcntl`, assumes the
POSIX venv layout, and ships extensionless executables; none of that has a
Windows branch. `py -3 rolescan.py --help` works for a quick look, but `setup`,
`ingest` and `poll` are not supported there yet. WSL2 is the supported route.

## Docker

Useful when the host has no Python at all, or you want the state isolated.

```bash
docker build -t rolescan .
docker run --rm --user "$(id -u):$(id -g)" rolescan doctor --json
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/data:/app/data" rolescan personas
```

`docker compose run --rm rolescan doctor` does the same through the compose file.
The image excludes the browser and the NLC hub on purpose; both stay host-side.
Always pass `--user`, otherwise the mounted `data/` is written as root.

## Scheduler

Print the resolved values first; the templates below use them.

```bash
python3 rolescan.py doctor --paths
# python=/path/to/venv/bin/python
# clone=/path/to/rolescan
# data=/path/to/rolescan/data
```

### cron (Linux, WSL)

```cron
*/30 * * * * cd CLONE && venv/bin/python rolescan.py poll   >> DATA/poll.log 2>&1
*/15 * * * * cd CLONE && venv/bin/python rolescan.py ingest >> DATA/run.log  2>&1
```

### launchd (macOS)

Save as `~/Library/LaunchAgents/dev.rolescan.plist`, then
`launchctl load ~/Library/LaunchAgents/dev.rolescan.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>dev.rolescan</string>
  <key>ProgramArguments</key>
  <array><string>CLONE/venv/bin/python</string><string>CLONE/rolescan.py</string><string>ingest</string></array>
  <key>WorkingDirectory</key><string>CLONE</string>
  <key>StartInterval</key><integer>900</integer>
  <key>StandardOutPath</key><string>DATA/run.log</string>
  <key>StandardErrorPath</key><string>DATA/run.err</string>
</dict></plist>
```

### Task Scheduler (Windows)

WSL2 users should schedule inside WSL with cron. For a native attempt:

```powershell
schtasks /Create /SC MINUTE /MO 15 /TN rolescan ^
  /TR "wsl.exe -e bash -lc 'cd /path/to/rolescan && venv/bin/python rolescan.py ingest'"
```

## Environment

| Variable | Meaning |
|---|---|
| `JOBKIT_DATA` | where state lives (default `./data`) |
| `JOBKIT_FILTERS` | filters document (default `filters/active.json`, else the example) |
| `JOBKIT_ENV` | env file (default `./.env`; blank disables it) |
| `NOTIFY` | `print`, `webhook` or `discord` |

## NLC gate (optional)

`bin/check-nlc.sh` needs the NLC compiler 0.8.0 on the host:

```bash
curl -fsSL https://raw.githubusercontent.com/Zygotic-AI/Natural-Language-Compiler/main/scripts/install.sh | NLC_VERSION=0.8.0 bash
bin/check-nlc.sh
```

It is separate from `bin/check.sh` because it needs a hub that the container and
Windows do not have. The package's rules live in `rules/` either way.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python >= 3.12 required` | install 3.12+; `rolescan setup --python /path/to/python3.12` |
| `CORE_NOT_READY: filters` | the message names the JSON pointer; `filters/README.md` explains each field |
| `browser WARN` | optional; the board poller needs no browser |
| `docker: permission denied` writing data | pass `--user "$(id -u):$(id -g)"` |
| `NLC:NOT_MET install hub first` | install the compiler above, or skip this gate |
