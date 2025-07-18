#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]
use std::process::{Command, Stdio};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::net::{SocketAddr, IpAddr};
use std::str::FromStr;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{mpsc, oneshot, Mutex, Semaphore};
use tokio::time::{self, Duration};
use std::sync::Arc;
use csv::Writer;
use chrono::{DateTime, Utc};

#[derive(Debug, Deserialize)]
#[serde(tag = "cmd")]
enum ClientCommand {
    #[serde(rename = "start")]
    Start { ips: Vec<String>, interval: u64 },
    #[serde(rename = "set_interval")]
    SetInterval { interval: u64 },
    #[serde(rename = "stop")]
    Stop,
    #[serde(rename = "export")]
    Export,
}

#[derive(Debug, Serialize, Clone)]
struct PingStat {
    ip: String,
    pass: u64,
    fail: u64,
    disconnected_time: u64, // ms
    last_ping_time: u64, // timestamp
}

type SharedStats = Arc<Mutex<HashMap<String, PingStat>>>;

enum PingControl {
    Start(Vec<String>, u64),
    SetInterval(u64),
    Stop,
    Export(oneshot::Sender<Vec<PingStat>>),
}

struct PingManager {
    tasks: HashMap<String, mpsc::Sender<PingTaskControl>>,
    interval: u64,
}

enum PingTaskControl {
    UpdateInterval(u64),
    Stop,
}

// Semaphore to limit concurrent pings
static PING_SEMAPHORE: tokio::sync::OnceCell<Arc<Semaphore>> = tokio::sync::OnceCell::const_new();

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize semaphore with 50 concurrent pings
    PING_SEMAPHORE.set(Arc::new(Semaphore::new(50))).unwrap();
    
    let listener = TcpListener::bind("127.0.0.1:7878").await?;
    println!("Backend listening on 127.0.0.1:7878");

    let stats: SharedStats = Arc::new(Mutex::new(HashMap::new()));
    let manager = Arc::new(Mutex::new(PingManager {
        tasks: HashMap::new(),
        interval: 1000,
    }));
    let (ctrl_tx, mut ctrl_rx) = mpsc::unbounded_channel();

    // Task: manage control commands
    let stats_ctrl = stats.clone();
    let manager_ctrl = manager.clone();
    tokio::spawn(async move {
        while let Some(cmd) = ctrl_rx.recv().await {
            match cmd {
                PingControl::Start(ips, interval) => {
                    let mut m = manager_ctrl.lock().await;
                    m.interval = interval;
                    
                    // Stop tasks for IPs not in the new list
                    let new_ips: HashSet<_> = ips.iter().cloned().collect();
                    let old_ips: HashSet<_> = m.tasks.keys().cloned().collect();
                    
                    for ip in old_ips.difference(&new_ips) {
                        if let Some(tx) = m.tasks.remove(ip) {
                            let _ = tx.send(PingTaskControl::Stop).await;
                        }
                        stats_ctrl.lock().await.remove(ip);
                    }
                    
                    // Start new tasks with staggered start
                    let mut start_delay = 0;
                    for ip in new_ips.difference(&old_ips) {
                        let (tx, rx) = mpsc::channel(1);
                        m.tasks.insert(ip.clone(), tx);
                        let stats = stats_ctrl.clone();
                        let ip_clone = ip.clone();
                        
                        tokio::spawn(async move {
                            if start_delay > 0 {
                                tokio::time::sleep(Duration::from_millis(start_delay)).await;
                            }
                            ping_task(ip_clone, interval, stats, rx).await;
                        });
                        
                        start_delay += 10;
                    }
                    
                    // Update interval for existing tasks
                    for ip in new_ips.intersection(&old_ips) {
                        if let Some(tx) = m.tasks.get(ip) {
                            let _ = tx.send(PingTaskControl::UpdateInterval(interval)).await;
                        }
                    }
                }
                PingControl::SetInterval(interval) => {
                    let mut m = manager_ctrl.lock().await;
                    m.interval = interval;
                    for tx in m.tasks.values() {
                        let _ = tx.send(PingTaskControl::UpdateInterval(interval)).await;
                    }
                }
                PingControl::Stop => {
                    let mut m = manager_ctrl.lock().await;
                    for (_ip, tx) in m.tasks.drain() {
                        let _ = tx.send(PingTaskControl::Stop).await;
                    }
                    stats_ctrl.lock().await.clear();
                }
                PingControl::Export(resp_tx) => {
                    let stats = stats_ctrl.lock().await;
                    let data: Vec<PingStat> = stats.values().cloned().collect();
                    let _ = resp_tx.send(data);
                }
            }
        }
    });

    loop {
        let (socket, addr) = listener.accept().await?;
        let stats = stats.clone();
        let ctrl_tx = ctrl_tx.clone();
        let manager = manager.clone();
        tokio::spawn(async move {
            if let Err(e) = handle_client(socket, addr, stats, ctrl_tx, manager).await {
                eprintln!("Client error: {}", e);
            }
        });
    }


}

async fn handle_client(
    socket: TcpStream,
    _addr: SocketAddr,
    stats: SharedStats,
    ctrl_tx: mpsc::UnboundedSender<PingControl>,
    _manager: Arc<Mutex<PingManager>>,
) -> Result<(), Box<dyn std::error::Error>> {
    let (reader, mut writer) = socket.into_split();
    let mut reader = BufReader::new(reader).lines();

    // Task to send stats to client every 500ms
    let stats_send = stats.clone();
    let writer = Arc::new(Mutex::new(writer));
    let writer_send = writer.clone();
    tokio::spawn(async move {
        let mut send_interval = time::interval(Duration::from_millis(500));
        loop {
            send_interval.tick().await;
            let stats_guard = stats_send.lock().await;
            let mut writer_guard = writer_send.lock().await;
            for stat in stats_guard.values() {
                if let Ok(msg) = serde_json::to_string(stat) {
                    let _ = writer_guard.write_all(msg.as_bytes()).await;
                    let _ = writer_guard.write_all(b"\n").await;
                }
            }
        }
    });

    while let Some(line) = reader.next_line().await? {
        if let Ok(cmd) = serde_json::from_str::<ClientCommand>(&line) {
            match cmd {
                ClientCommand::Start { ips, interval } => {
                    println!("Starting ping for {} IPs with interval {}ms", ips.len(), interval);
                    ctrl_tx.send(PingControl::Start(ips, interval))?;
                }
                ClientCommand::SetInterval { interval } => {
                    ctrl_tx.send(PingControl::SetInterval(interval))?;
                }
                ClientCommand::Stop => {
                    ctrl_tx.send(PingControl::Stop)?;
                }
                ClientCommand::Export => {
                    let (resp_tx, resp_rx) = oneshot::channel();
                    ctrl_tx.send(PingControl::Export(resp_tx))?;
                    if let Ok(data) = resp_rx.await {
                        export_csv(&data).await?;
                        let mut writer_guard = writer.lock().await;
                        let _ = writer_guard.write_all(b"Exported\n").await;
                    }
                }
            }
        }
    }
    ctrl_tx.send(PingControl::Stop)?;
    Ok(())
}

async fn export_csv(stats: &[PingStat]) -> Result<(), Box<dyn std::error::Error>> {
    let mut wtr = Writer::from_path("ping_stats_export.csv")?;
    wtr.write_record(&["IP", "Pass", "Fail", "Disconnected Time (ms)", "Last Ping Time"])?;
    
    for stat in stats {
        let last_ping = if stat.last_ping_time > 0 {
            DateTime::<Utc>::from(
                std::time::SystemTime::UNIX_EPOCH + Duration::from_secs(stat.last_ping_time)
            ).format("%Y-%m-%d %H:%M:%S").to_string()
        } else {
            "N/A".to_string()
        };
        wtr.write_record(&[
            stat.ip.as_str(),
            stat.pass.to_string().as_str(),
            stat.fail.to_string().as_str(),
            stat.disconnected_time.to_string().as_str(),
            last_ping.as_str(),
        ])?;
    }
    
    wtr.flush()?;
    Ok(())
}

async fn ping_task(
    ip: String,
    mut interval: u64,
    stats: SharedStats,
    mut ctrl_rx: mpsc::Receiver<PingTaskControl>,
) {
    let mut pass = 0u64;
    let mut fail = 0u64;
    let disconnected_time = 0u64; // Set to 0 as per requirement
    let mut ticker = time::interval(Duration::from_millis(interval));
    
    let ip_addr = match IpAddr::from_str(&ip) {
        Ok(addr) => addr,
        Err(_) => {
            eprintln!("Invalid IP address: {}", ip);
            return;
        }
    };

    println!("Started ping task for {}", ip);
    
    // Initialize stats immediately
    {
        let mut stats_guard = stats.lock().await;
        stats_guard.insert(
            ip.clone(),
            PingStat {
                ip: ip.clone(),
                pass: 0,
                fail: 0,
                disconnected_time: 0,
                last_ping_time: 0,
            },
        );
    }

    loop {
        tokio::select! {
            _ = ticker.tick() => {
                let timestamp = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs();
                
                let success = timeout_ping(&ip_addr).await;
                
                if success {
                    pass += 1;
                } else {
                    fail += 1;
                }

                let mut stats_guard = stats.lock().await;
                stats_guard.insert(
                    ip.clone(),
                    PingStat {
                        ip: ip.clone(),
                        pass,
                        fail,
                        disconnected_time,
                        last_ping_time: timestamp,
                    },
                );
            }
            Some(ctrl) = ctrl_rx.recv() => {
                match ctrl {
                    PingTaskControl::UpdateInterval(new_interval) => {
                        interval = new_interval;
                        ticker = time::interval(Duration::from_millis(interval));
                        println!("Updated interval for {} to {}ms", ip, interval);
                    }
                    PingTaskControl::Stop => {
                        println!("Stopped ping task for {}", ip);
                        break;
                    }
                }
            }
        }
    }
}

async fn timeout_ping(ip: &IpAddr) -> bool {
    let semaphore = PING_SEMAPHORE.get().unwrap();
    let _permit = semaphore.acquire().await.unwrap();
    
    let timeout_duration = Duration::from_secs(2);
    
    match tokio::time::timeout(timeout_duration, async_ping(ip)).await {
        Ok(result) => result,
        Err(_) => false,
    }
}

async fn async_ping(ip: &IpAddr) -> bool {
    let ip_str = ip.to_string();
    tokio::task::spawn_blocking(move || {
        system_ping(&ip_str)
    }).await.unwrap_or(false)
}

// fn system_ping(ip: &str) -> bool {
//     #[cfg(target_os = "windows")]
//     let output = Command::new("ping")
//         .args(&["-n", "1", "-w", "1000", ip])
//         .output();
    
//     #[cfg(not(target_os = "windows"))]
//     let output = Command::new("ping")
//         .args(&["-c", "1", "-W", "1", ip])
//         .output();
    
//     match output {
//         Ok(output) => output.status.success(),
//         Err(_) => false,
//     }
// }



#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt; // Để dùng .creation_flags()

#[cfg(target_os = "windows")]
pub fn system_ping(ip: &str) -> bool {
    const CREATE_NO_WINDOW: u32 = 0x08000000;

    let output = Command::new("ping")
        .args(["-n", "1", "-w", "1000", ip])
        .creation_flags(CREATE_NO_WINDOW)  // Ngăn mở cửa sổ CMD
        .stdout(Stdio::null())             // Không in ra stdout
        .stderr(Stdio::null())             // Không in lỗi ra stderr
        .output();

    output.map(|o| o.status.success()).unwrap_or(false)
}

#[cfg(not(target_os = "windows"))]
pub fn system_ping(ip: &str) -> bool {
    let output = Command::new("ping")
        .args(["-c", "1", "-W", "1", ip])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .output();

    output.map(|o| o.status.success()).unwrap_or(false)
}
