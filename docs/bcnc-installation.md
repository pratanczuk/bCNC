# bCNC Installation (Windows, Linux, or macOS)

An advanced, feature-rich plotter control interface and G-code sender written in Python.
This fork includes custom enhancements tailored for digital vinyl/foil plotters and specialized GRBL/grblHAL workflows.

## Table of Contents
- [Features](#features)
- [Quick Installation (Pre-built Installers)](#quick-installation-pre-built-installers)
- [Manual Installation Prerequisites](#manual-installation-prerequisites)
- [Windows Setup (Manual)](#windows-setup-manual)
- [Linux Setup (Ubuntu/Debian)](#linux-setup-ubuntudebian)
- [macOS Setup](#macos-setup)
- [Quick Start](#quick-start)
- [Troubleshooting & Tips](#troubleshooting--tips)

## Features
- **Cross-Platform**: Runs natively on Windows, Linux, and macOS.
- **GRBL & grblHAL Integration**: Fast, reliable streaming with real-time position monitoring and override controls.
- **G-Code Manipulation**: Integrated CAM functions, path optimization, auto-leveling, and post-processor plugins.
- **Advanced Plotter/Cutting Support**: Enhanced handling for vinyl cutters, pen plotters, and custom multi-axis toolheads.

## Quick Installation (Pre-built Installers)
If you do not want to configure a Python environment manually, pre-compiled standalone installers/executables are available for direct download:

1. Go to the repository **Releases** page on GitHub.
2. Download the latest pre-built package for your operating system (for example, `.exe` for Windows).
3. Run the installer or execute the binary directly.

## Manual Installation Prerequisites
If running directly from source code, bCNC requires:
- Python 3.7+
- `tkinter` (GUI framework)
- `pyserial` (communication backend)

## Windows Setup (Manual)
1. Download and install Python 3.

   > ⚠️ Important: During installation, check **Add Python to PATH**.

2. Open **Command Prompt** (`Win + R`, type `cmd`, press Enter).
3. Clone the repository:

```bash
git clone https://github.com/pratanczuk/bCNC.git
cd bCNC
```

## Linux Setup (Ubuntu/Debian)
1. Install system dependencies and Python tools.
2. Clone the repository and run bCNC from source.

```bash
git clone https://github.com/pratanczuk/bCNC.git
cd bCNC
```

## macOS Setup
1. Install Python 3 (for example, via official installer or Homebrew).
2. Clone the repository and run bCNC from source.

```bash
git clone https://github.com/pratanczuk/bCNC.git
cd bCNC
```

## Quick Start
After installation:
1. Launch bCNC.
2. Configure your machine connection (serial or socket).
3. Load or create G-code.
4. Test movement safely before production cuts.

## Troubleshooting & Tips
- Verify USB/serial permissions if the controller is not detected.
- Confirm baud rate and controller firmware settings.
- Use stable network connectivity for remote/socket operation.
