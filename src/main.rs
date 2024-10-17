use std::fs::OpenOptions;
use std::io::Write;
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};
use chrono::Local;
use std::sync::{Arc, Mutex};

fn ping_ip(ip_address: String, log_file: String, packet_size: u32, seq_num: Arc<Mutex<u32>>) {
    loop {
        let start_time = Instant::now();
        let result = if cfg!(target_os = "windows") {
            Command::new("ping")
                .arg("-n").arg("1")
                .arg("-l").arg(packet_size.to_string())
                .arg(&ip_address)
                .output()
        } else {
            Command::new("ping")
                .arg("-c").arg("1")
                .arg("-s").arg(packet_size.to_string())
                .arg(&ip_address)
                .output()
        };

        match result {
            Ok(output) => {
                let output_str = String::from_utf8_lossy(&output.stdout);
                if (cfg!(target_os = "windows") && !output_str.contains("Reply from")) ||
                   (!cfg!(target_os = "windows") && !output_str.contains("1 packets transmitted, 1 received")) {
                    handle_timeout(&ip_address, &log_file, start_time, Arc::clone(&seq_num));
                } else {
                    let mut seq = seq_num.lock().unwrap();
                    *seq += 1;
                    println!("Sequence {}, IP {}, Result: {}", *seq, ip_address, output_str.trim());
                }
            }
            Err(e) => {
                println!("Failed to ping IP {}: {}", ip_address, e);
            }
        }

        thread::sleep(Duration::from_secs(1));
    }
}

fn handle_timeout(ip_address: &str, log_file: &str, start_time: Instant, seq_num: Arc<Mutex<u32>>) {
    let timestamp = Local::now().format("%Y-%m-%d %H:%M:%S").to_string();
    let duration = start_time.elapsed().as_secs_f32();
    let mut seq = seq_num.lock().unwrap();
    
    write_to_csv(log_file, *seq, &timestamp, duration);
    println!("Request timeout: Sequence {}, IP {}", *seq, ip_address);
    *seq += 1;
}

fn write_to_csv(file_path: &str, sequence_number: u32, timestamp: &str, duration: f32) {
    let mut file = OpenOptions::new().append(true).create(true).open(file_path).expect("Cannot open file");
    writeln!(file, "{},{},{}", sequence_number, timestamp, duration).expect("Cannot write to file");
}

fn main() {
    let mut num_ips = String::new();
    println!("How many IP addresses do you want to ping?");
    std::io::stdin().read_line(&mut num_ips).expect("Failed to read input");
    let num_ips: usize = num_ips.trim().parse().expect("Please enter a valid number");

    let mut ip_addresses = Vec::new();
    for i in 0..num_ips {
        let mut ip_address = String::new();
        println!("Enter IP address {}: ", i + 1);
        std::io::stdin().read_line(&mut ip_address).expect("Failed to read input");
        ip_addresses.push(ip_address.trim().to_string());
    }

    let mut packet_size = String::new();
    println!("Enter packet size (bytes): ");
    std::io::stdin().read_line(&mut packet_size).expect("Failed to read input");
    let packet_size: u32 = packet_size.trim().parse().expect("Please enter a valid packet size");

    let mut threads = vec![];

    for ip in ip_addresses {
        let log_file = format!("log_{}.csv", ip);
        let seq_num = Arc::new(Mutex::new(1));
        let ip_clone = ip.clone();
        let seq_clone = Arc::clone(&seq_num);
        threads.push(thread::spawn(move || {
            ping_ip(ip_clone, log_file, packet_size, seq_clone);
        }));
    }

    for thread in threads {
        thread.join().expect("Thread failed");
    }

    println!("Exit program by user.");
}
