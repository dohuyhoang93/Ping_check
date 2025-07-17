use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::Write;
use std::net::{SocketAddr, IpAddr};
use std::str::FromStr;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{mpsc, oneshot, Mutex};
use tokio::time::{self, Duration, Instant};
use std::sync::Arc;

// ICMP ping thực tế
use ping::ping;

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

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let listener = TcpListener::bind("127.0.0.1:7878").await?;
    println!("Backend listening on 127.0.0.1:7878");

    let stats: SharedStats = Arc::new(Mutex::new(HashMap::new()));
    let manager = Arc::new(Mutex::new(PingManager {
        tasks: HashMap::new(),
        interval: 1000,
    }));
    let (ctrl_tx, mut ctrl_rx) = mpsc::unbounded_channel();

    // Task: quản lý lệnh điều khiển
    let stats_ctrl = stats.clone();
    let manager_ctrl = manager.clone();
    tokio::spawn(async move {
        while let Some(cmd) = ctrl_rx.recv().await {
            match cmd {
                PingControl::Start(ips, interval) => {
                    let mut m = manager_ctrl.lock().await;
                    m.interval = interval;
                    // Stop các task cũ không còn trong danh sách
                    let new_ips: HashSet<_> = ips.iter().cloned().collect();
                    let old_ips: HashSet<_> = m.tasks.keys().cloned().collect();
                    for ip in old_ips.difference(&new_ips) {
                        if let Some(tx) = m.tasks.remove(ip) {
                            let _ = tx.send(PingTaskControl::Stop).await;
                        }
                        stats_ctrl.lock().await.remove(ip);
                    }
                    // Start task mới
                    for ip in new_ips.difference(&old_ips) {
                        let (tx, rx) = mpsc::channel(1);
                        m.tasks.insert(ip.clone(), tx);
                        let stats = stats_ctrl.clone();
                        let ip_clone = ip.clone();
                        tokio::spawn(ping_task(ip_clone, interval, stats, rx));
                    }
                    // Update interval cho các task còn lại
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

    // Task gửi kết quả về client mỗi 1s
    let stats_send = stats.clone();
    let writer = Arc::new(Mutex::new(writer));
    let writer_send = writer.clone();
    tokio::spawn(async move {
        let mut send_interval = time::interval(Duration::from_millis(1000));
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
                        export_csv(&data)?;
                        let mut writer_guard = writer.lock().await;
                        let _ = writer_guard.write_all(b"Exported\n").await;
                    }
                }
            }
        }
    }
    // Khi client ngắt kết nối, dừng toàn bộ task
    ctrl_tx.send(PingControl::Stop)?;
    Ok(())
}

fn export_csv(stats: &[PingStat]) -> Result<(), Box<dyn std::error::Error>> {
    let mut file = File::create("ping_stats_export.csv")?;
    writeln!(file, "ip,pass,fail,disconnected_time")?;
    for s in stats {
        writeln!(file, "{},{},{},{}", s.ip, s.pass, s.fail, s.disconnected_time)?;
    }
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
    let mut disconnected_time = 0u64;
    let mut last_fail: Option<Instant> = None;
    let mut ticker = time::interval(Duration::from_millis(interval));
    let ip_addr = match IpAddr::from_str(&ip) {
        Ok(addr) => addr,
        Err(_) => return,
    };
    loop {
        tokio::select! {
            _ = ticker.tick() => {
                // Clone ip_addr vì IpAddr không Copy
                let success = real_ping(&ip_addr);
                if success {
                    pass += 1;
                    last_fail = None;
                } else {
                    fail += 1;
                    let now = Instant::now();
                    if let Some(last) = last_fail {
                        disconnected_time += now.duration_since(last).as_millis() as u64;
                    } else {
                        last_fail = Some(now);
                    }
                }
                let mut stats_guard = stats.lock().await;
                stats_guard.insert(
                    ip.clone(),
                    PingStat {
                        ip: ip.clone(),
                        pass,
                        fail,
                        disconnected_time,
                    },
                );
            }
            Some(ctrl) = ctrl_rx.recv() => {
                match ctrl {
                    PingTaskControl::UpdateInterval(new_interval) => {
                        interval = new_interval;
                        ticker = time::interval(Duration::from_millis(interval));
                    }
                    PingTaskControl::Stop => {
                        break;
                    }
                }
            }
        }
    }
}

fn real_ping(ip: &IpAddr) -> bool {
    // Sử dụng crate ping để gửi ICMP, timeout 1s
    match ping(*ip, None, None, None, None, None) {
        Ok(_) => true, // Nếu không lỗi là thành công
        Err(_) => false,
    }
}
