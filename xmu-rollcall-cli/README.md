# xmu-rollcall-cli

**CatNebulaaaa Fork** — based on [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot), with timetable number-code fallback and five Xiang'an campus radar presets enabled by plain `xmu start`. Original author credit and the MIT license are preserved.

A command-line tool for monitoring and auto-answering Tronclass rollcalls at Xiamen University.

> This project is intended for personal learning and automation convenience. Use it at your own risk and comply with your school's rules.

## Features

- Login with XMU unified authentication through `xmulogin`
- Continuous rollcall polling (1-second interval)
- Automatic handling for:
  - Number rollcalls (fetch number code and answer directly)
  - Radar rollcalls (five WGS84 building presets, tried in order with 5-second spacing)
- Multi-account management in one local config
- Session cookie cache and refresh support

## Installation

Install this fork from GitHub:

```bash
python -m pip install --upgrade "git+https://github.com/CatNebulaaaa/XMU-Rollcall-Bot.git#subdirectory=xmu-rollcall-cli"
```

After installation, these command aliases are available:

- `xmu`
- `xmu-rollcall-cli`
- `XMUrollcall-cli`

## Quick Start

1. Configure at least one account:

```bash
xmu config
```

2. (Optional) Switch active account:

```bash
xmu switch
```

3. Start monitoring:

```bash
xmu start
```

4. If session becomes invalid, refresh cookies:

```bash
xmu refresh
```

## Commands

- `xmu config` - Add/delete accounts and set current account
- `xmu switch` - Switch the current account
- `xmu start` - Start rollcall monitoring loop
- `xmu start --radar-points points.json` - Override the bundled five-point preset
- `xmu start --latitude LAT --longitude LON` - Use one actual WGS84 location instead
- `xmu refresh` - Remove cached cookies for current account
- `xmu --help` - Show help

## Configuration

The package stores local data in a `.xmu_rollcall` directory:

1. `XMU_ROLLCALL_CONFIG_DIR` (if set)
2. `~/.xmu_rollcall` (default)
3. `./.xmu_rollcall` (fallback when home is not writable)

Main files:

- `config.json`: account list and selected account
- `<account_id>.json`: cached cookies per account

Example (custom config directory):

```bash
export XMU_ROLLCALL_CONFIG_DIR="$HOME/Documents/.xmu_rollcall"
```

## Limitations

- QR code rollcalls are currently **not supported**.
- This tool depends on Tronclass/XMU API behavior and may break if upstream endpoints change.
- The 48 regression tests use simulated responses. Real classroom attendance has not been verified; building centers may differ from the classroom location.

## Supported Python Versions

- Python 3.7+

## Project Links

- Homepage: https://github.com/CatNebulaaaa/XMU-Rollcall-Bot
- Issues: https://github.com/CatNebulaaaa/XMU-Rollcall-Bot/issues
- Upstream: https://github.com/KrsMt-0113/XMU-Rollcall-Bot

## License

MIT License
