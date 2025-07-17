# Specification Document: Multi-IP Real-Time Ping Monitoring System

## Overview

This system consists of a **Python GUI frontend using ttkbootstrap** and a **Rust backend using Tokio** to manage high-performance asynchronous multi-IP ping operations. Communication between frontend and backend is handled via a lightweight **custom TCP socket protocol**. The system is designed for real-time statistics, extensibility, and clean resource usage without CSV-based I/O during active monitoring.

---

## System Architecture

### Frontend: Python + ttkbootstrap GUI

- **Technology**: Python 3.10+, ttkbootstrap, socket, threading
- **Role**: Controls and displays ping statistics, communicates with the backend, handles user input

#### Key Features

- **IP List View**: Each IP displayed as a row:
  - IP Address
  - Ping Result Rate (% Pass / % Fail)
  - Total Attempt Count
  - Disconnection Duration (accumulated time offline)
- **Toolbar Controls**:
  - Start / Stop button
  - Import IPs from `.txt`
  - Export summary CSV (optional, on user demand)
  - Ping interval dropdown (e.g., 1s, 2s, 5s)
- **Live Theme Switcher**:
  - Fully reactive to ttkbootstrap theme changes in real-time without restarting the app
- **Status Panel**:
  - Total IPs, Active Threads, Backend Status (Connected/Disconnected)

---

### Backend: Rust with Tokio

- **Technology**: Rust, Tokio, ICMP/UDP crate (e.g., `surrealdb/ping` or similar), Serde, socket
- **Role**: Manages parallel pinging, time statistics, handles requests from frontend, sends structured reports

#### Responsibilities

- Accepts list of IPs and interval settings from GUI
- Spawns async tasks to ping each IP concurrently
- Collects and computes:
  - Count of success/fail
  - Fail rate (percentage)
  - Accumulated disconnection time
- Sends JSON-formatted updates via TCP every N seconds (\~1s configurable)
- Listens for control commands (update interval, stop ping, export, etc.)

---

## Communication Protocol

### Transport: TCP socket (Rust server <--> Python client)

#### Messages from GUI to Backend:

```json
{
  "cmd": "start",
  "ips": ["192.168.1.1", "192.168.1.2"],
  "interval": 1000
}
```

```json
{
  "cmd": "set_interval",
  "interval": 500
}
```

```json
{
  "cmd": "stop"
}
```

```json
{
  "cmd": "export"
}
```

#### Messages from Backend to GUI:

```json
{
  "ip": "192.168.1.2",
  "pass": 120,
  "fail": 10,
  "disconnected_time": 3000
}
```

- Format: one JSON message per IP per interval window

---

## Optional Features (Future)

- Live chart of ping delay per IP
- Auto-sort IPs by fail rate
- Highlight IPs with >50% failure in red
- Multilingual support (EN, VI)
- Remote backend deployment support

---

## Packaging & Distribution

- Backend compiled to standalone executable using `cargo build --release`
- GUI packaged with `PyInstaller` or `Nuitka`, bundled with Python runtime
- Final deployment: single folder with `ping_client.exe` + `ping_backend.exe`

---

## Performance Expectations

- Capable of monitoring 500+ IPs concurrently with <10% CPU on modern CPUs
- Latency update under 1s using async runtime (Tokio + socket)
- Memory usage < 100MB typical

---

## License & Authors

- License: GPL 3.0
- Authors: Hoang Do Huy and contributors
- GitHub Repository: [https://github.com/dohuyhoang93/Ping_check](https://github.com/dohuyhoang93/Ping_check) (base architecture)

