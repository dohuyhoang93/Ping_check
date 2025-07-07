# Ping Check

A simple multithreaded Rust program to check network reachability of multiple IP addresses using `ping`.

## Features

- Read IPs from a text file (`ips.txt`)
- Spawn a thread for each IP to ping continuously every 5 seconds
- Compatible with Windows, Linux, and macOS
- Shows real-time reachability status in the terminal

## Usage

1. Add your IPs (one per line) in a file named `ips.txt`
2. Build and run the program with Cargo:

```bash
cargo run --release
```

3. The console will continuously display the reachability status of each IP

## Example `ips.txt`

```
8.8.8.8
1.1.1.1
192.168.1.1
```
