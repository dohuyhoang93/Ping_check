fn main() {
    // Ngăn Windows mở console cho chính process `check_ping.exe`
    println!("cargo:rustc-link-arg=/SUBSYSTEM:WINDOWS");
}
