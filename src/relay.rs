use anyhow::Result;
use serde_json::{Value, json};
use std::{
    collections::{HashSet, VecDeque},
    time::Duration,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::{broadcast, mpsc},
    time::{sleep, timeout},
};

#[derive(Default)]
pub struct Dedup {
    seen: HashSet<(String, u64)>,
    order: VecDeque<(String, u64)>,
}

impl Dedup {
    pub fn first(&mut self, row: &Value) -> bool {
        let Some(id) = row["update_id"].as_u64() else {
            return false;
        };
        let Some(symbol) = row["symbol"].as_str() else {
            return false;
        };
        let key = (symbol.to_owned(), id);
        if !self.seen.insert(key.clone()) {
            return false;
        }
        self.order.push_back(key);
        if self.order.len() > 65536 {
            self.seen.remove(&self.order.pop_front().unwrap());
        }
        true
    }
}

pub async fn sender(listen: &[String]) -> Result<broadcast::Sender<Vec<u8>>> {
    let (frames, _) = broadcast::channel::<Vec<u8>>(8192);
    for address in listen {
        let listener = TcpListener::bind(address).await?;
        let frames = frames.clone();
        tokio::spawn(async move {
            while let Ok((mut socket, _)) = listener.accept().await {
                let mut input = frames.subscribe();
                tokio::spawn(async move {
                    let _ = socket.set_nodelay(true);
                    if socket.write_all(super::journal::MAGIC).await.is_err() {
                        return;
                    }
                    while let Ok(frame) = input.recv().await {
                        if !matches!(
                            timeout(Duration::from_secs(2), socket.write_all(&frame)).await,
                            Ok(Ok(()))
                        ) {
                            break;
                        }
                    }
                });
            }
        });
    }
    Ok(frames)
}

async fn read(address: &str, link: usize, output: &mpsc::Sender<Value>) -> Result<()> {
    let mut socket = timeout(Duration::from_secs(5), TcpStream::connect(address)).await??;
    let mut magic = [0; 8];
    timeout(Duration::from_secs(5), socket.read_exact(&mut magic)).await??;
    anyhow::ensure!(&magic == super::journal::MAGIC, "invalid relay protocol");
    loop {
        let size = timeout(Duration::from_secs(300), socket.read_u32_le()).await?? as usize;
        super::journal::valid_size(size)?;
        let mut payload = vec![0; size];
        timeout(Duration::from_secs(5), socket.read_exact(&mut payload)).await??;
        let now = super::now_ns();
        let mut row = super::journal::parse(&payload)?;
        anyhow::ensure!(row["kind"] == "binance_bbo", "invalid relay record");
        row["ohio_recv_ns"] = json!(now);
        row["relay_link"] = json!(link);
        output.send(row).await?;
    }
}

pub async fn receive(address: String, link: usize, output: mpsc::Sender<Value>) {
    while !output.is_closed() {
        let _ = read(&address, link, &output).await;
        if output
            .send(json!({"kind":"relay_gap","relay_link":link,"recv_ns":super::now_ns()}))
            .await
            .is_err()
        {
            break;
        }
        sleep(Duration::from_millis(500)).await;
    }
}
