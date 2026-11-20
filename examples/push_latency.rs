use std::io::{self, BufRead, BufWriter, Write};
#[path = "../src/journal.rs"]
mod journal;
use anyhow::{Context, Result, ensure};
use base64::{Engine, engine::general_purpose::STANDARD};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use sha3::{Digest, Keccak256};
use std::collections::{HashMap, HashSet};
use std::time::Instant;
use tokio::sync::mpsc;
use tokio::time::{Duration, timeout};
use tokio_tungstenite::{
    connect_async, tungstenite::Message, tungstenite::client::IntoClientRequest,
};

#[path = "../src/pyth.rs"]
mod pyth;

const SOURCE: &str = "e844701934d9c6085b292e428f41b911cc0b3872";
const PYTH: &str = "30a88bf894d1b806125a23ebf23d715496fd7102";
const TOPIC: &str = "0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586";
const FEEDS: [&str; 2] = [
    "0x8dfdc825dd0453e7c80b1c1d32ae910e35d6efe9000000000000000012375400",
    "0x0000000000000000000000000000000000000000000000000000000000000cf4",
];

fn rlp(input: &mut &[u8]) -> Option<(bool, Vec<u8>)> {
    let tag = *input.first()?;
    if tag < 128 {
        *input = &input[1..];
        return Some((false, vec![tag]));
    }
    let (list, base) = if tag >= 192 {
        (true, 192)
    } else {
        (false, 128)
    };
    let n = (tag - base) as usize;
    let (offset, len) = if n <= 55 {
        (1, n)
    } else {
        let offset = n - 55 + 1;
        let len = input
            .get(1..offset)?
            .iter()
            .try_fold(0usize, |v, b| v.checked_mul(256)?.checked_add(*b as usize))?;
        (offset, len)
    };
    let end = offset.checked_add(len)?;
    let data = input.get(offset..end)?.to_vec();
    *input = &input[end..];
    Some((list, data))
}

fn direct_tx(raw: &[u8]) -> Option<(String, String, String)> {
    let (fields, to_pos) = match *raw.first()? {
        1 => (&raw[1..], 4),
        2 | 4 => (&raw[1..], 5),
        192..=255 => (raw, 3),
        _ => return None,
    };
    let (true, fields) = rlp(&mut &*fields)? else {
        return None;
    };
    let mut fields = fields.as_slice();
    for _ in 0..to_pos {
        rlp(&mut fields)?;
    }
    let (_, to) = rlp(&mut fields)?;
    let to = hex::encode(to);
    if to != SOURCE && to != PYTH {
        return None;
    }
    rlp(&mut fields)?;
    let (_, calldata) = rlp(&mut fields)?;
    Some((
        format!("0x{}", hex::encode(Keccak256::digest(raw))),
        to,
        hex::encode(calldata),
    ))
}

fn visit(message: &[u8], depth: u8, visit_tx: &mut impl FnMut(&[u8])) {
    if depth > 16 {
        return;
    }
    match message.split_first() {
        Some((4, raw)) => visit_tx(raw),
        Some((3, mut batch)) => {
            while let Some((len, rest)) = batch.split_at_checked(8) {
                let len = u64::from_be_bytes(len.try_into().unwrap()) as usize;
                let Some((child, rest)) = rest.split_at_checked(len) else {
                    break;
                };
                visit(child, depth + 1, visit_tx);
                batch = rest;
            }
        }
        _ => {}
    }
}

enum Event {
    Tx(String, String, String, Instant, Option<String>),
    Log(Value, Instant),
    Bbo(Value, Instant),
}

async fn receive(feed: bool, url: String, out: mpsc::Sender<Event>) -> Result<()> {
    let mut request = url.into_client_request()?;
    if feed {
        request
            .headers_mut()
            .insert("arbitrum-feed-client-version", "2".parse()?);
    }
    let (mut ws, _) = timeout(Duration::from_secs(10), connect_async(request)).await??;
    if !feed {
        ws.send(Message::Text(
            json!({"jsonrpc":"2.0","id":1,"method":"eth_subscribe",
            "params":["logs",{"address":[format!("0x{SOURCE}"),format!("0x{PYTH}")],
            "topics":[TOPIC,FEEDS]}]})
            .to_string()
            .into(),
        ))
        .await?;
    }
    eprintln!(
        "{}",
        if feed {
            "feed_connected"
        } else {
            "logs_connected"
        }
    );
    while let Some(raw) = ws.next().await {
        let now = Instant::now();
        match raw? {
            Message::Text(text) => {
                let row: Value = serde_json::from_str(&text)?;
                ensure!(
                    row["error"].is_null(),
                    "subscription rejected: {}",
                    row["error"]
                );
                if feed {
                    for item in row["messages"].as_array().into_iter().flatten() {
                        let msg = &item["message"]["message"];
                        if msg["header"]["kind"] != 3 {
                            continue;
                        }
                        let Some(data) = msg["l2Msg"].as_str() else {
                            continue;
                        };
                        let data = STANDARD.decode(data)?;
                        let mut events = Vec::new();
                        visit(&data, 0, &mut |raw| {
                            if let Some((hash, to, input)) = direct_tx(raw) {
                                events.push(Event::Tx(
                                    hash,
                                    to,
                                    input,
                                    now,
                                    item["blockHash"].as_str().map(str::to_owned),
                                ));
                            }
                        });
                        for event in events {
                            out.send(event).await?;
                        }
                    }
                } else if row["method"] == "eth_subscription" {
                    out.send(Event::Log(row["params"]["result"].clone(), now))
                        .await?;
                }
            }
            Message::Ping(_) => ws.flush().await?,
            Message::Close(_) => break,
            _ => {}
        }
    }
    anyhow::bail!("socket closed")
}

async fn binance(out: mpsc::Sender<Event>) -> Result<()> {
    let (mut ws, _) = timeout(
        Duration::from_secs(10),
        connect_async("wss://stream.binance.com:443/ws/spcxbusdt@bookTicker"),
    )
    .await??;
    while let Some(frame) = ws.next().await {
        let now = Instant::now();
        match frame? {
            Message::Text(raw) => {
                out.send(Event::Bbo(serde_json::from_str(&raw)?, now))
                    .await?
            }
            Message::Ping(_) => ws.flush().await?,
            Message::Close(_) => break,
            _ => {}
        }
    }
    anyhow::bail!("Binance socket closed")
}

#[tokio::main]
async fn main() -> Result<()> {
    if std::env::args().nth(1).as_deref() == Some("replay") {
        return journal::replay(io::stdin().lock(), io::stdout().lock());
    }
    if std::env::args().nth(1).as_deref() == Some("encode") {
        let mut output = BufWriter::new(io::stdout().lock());
        output.write_all(journal::MAGIC)?;
        for line in io::stdin().lock().lines() {
            output.write_all(&journal::frame(&serde_json::from_str(&line?)?)?)?;
        }
        output.flush()?;
        return Ok(());
    }
    let duration = std::env::args()
        .nth(1)
        .context("expected duration seconds")?
        .parse()?;
    let (sender, mut input) = mpsc::channel(4096);
    let mut feed = tokio::spawn(receive(
        true,
        std::env::var("ROBIN_FEED_URL")
            .unwrap_or_else(|_| "wss://feed.mainnet.chain.robinhood.com".into()),
        sender.clone(),
    ));
    let mut logs = tokio::spawn(receive(
        false,
        std::env::var("ROBIN_WS_URL")
            .unwrap_or_else(|_| "wss://rpc-robinhood.blockmachine.io".into()),
        sender.clone(),
    ));
    let with_binance = std::env::var_os("ROBIN_PROBE_BINANCE").is_some();
    let mut binance = tokio::spawn(async move {
        if with_binance {
            binance(sender).await
        } else {
            std::future::pending().await
        }
    });
    let mut txs = HashMap::new();
    let mut pending = HashMap::new();
    let mut seen = HashSet::new();
    let start = Instant::now();
    let stop = tokio::time::sleep(Duration::from_secs(duration));
    tokio::pin!(stop);
    let mut count = 0;
    let mut output = BufWriter::new(io::stdout().lock());
    output.write_all(journal::MAGIC)?;
    let codebook: Vec<u64> =
        serde_json::from_str(include_str!("../scripts/metric_spread_codebook.json"))?;
    let ms = |t: Instant| t.duration_since(start).as_secs_f64() * 1000.0;
    loop {
        let event = tokio::select! {
            event = input.recv() => event.context("both streams closed")?,
            result = &mut feed => return result?.context("sequencer feed ended"),
            result = &mut logs => return result?.context("executed logs stream ended"),
            result = &mut binance => return result?.context("Binance stream ended"),
            _ = &mut stop => break,
        };
        let hash = match event {
            Event::Bbo(row, t) => {
                output.write_all(&journal::frame(
                    &json!({"kind":"bbo","ms":ms(t),"bid":row["b"],"ask":row["a"]}),
                )?)?;
                continue;
            }
            Event::Tx(hash, to, data, t, b) => {
                txs.entry(hash.clone()).or_insert((to, data, t, b));
                hash
            }
            Event::Log(log, t) => {
                let hash = log["transactionHash"]
                    .as_str()
                    .context("missing hash")?
                    .to_owned();
                if log["removed"] == true || !seen.insert(hash.clone()) {
                    continue;
                }
                if t.duration_since(start) < Duration::from_secs(5) {
                    continue;
                }
                count += 1;
                pending.insert(hash.clone(), (log, t));
                hash
            }
        };
        if !txs.contains_key(&hash) || !pending.contains_key(&hash) {
            continue;
        }
        let (to, data, feed_time, block) = txs.remove(&hash).unwrap();
        let (log, log_time) = pending.remove(&hash).unwrap();
        if block
            .as_deref()
            .is_some_and(|b| Some(b) != log["blockHash"].as_str())
        {
            continue;
        }
        let started = Instant::now();
        let price = if to == PYTH {
            pyth::decode(&format!("0x{data}"))
                .ok()
                .and_then(|r| r["price_e8"].as_u64())
        } else {
            let bytes = hex::decode(data)?;
            bytes
                .get(1..)
                .filter(|b| b.len() % 32 == 0)
                .and_then(|b| {
                    b.chunks_exact(32)
                        .filter(|w| w[31] == 0x54)
                        .max_by_key(|w| &w[24..31])
                })
                .filter(|w| w[4..6] != [255, 255] && codebook[w[4] as usize] < 1_000_000)
                .map(|w| {
                    let raw = u32::from_be_bytes(w[..4].try_into().unwrap());
                    u64::from(raw & ((1 << 27) - 1)) << (raw >> 27)
                })
        };
        let now = Instant::now();
        output.write_all(&journal::frame(
            &json!({"kind":"match","tx":hash,"oracle":if to==PYTH {"pyth"} else {"compressed"},
            "hash_verified":block.is_some(),"decoded":price.is_some(),"price_e8":price,"feed_ms":ms(feed_time),
            "log_ms":ms(log_time),"ready_ms":ms(now),"decode_us":now.duration_since(started).as_secs_f64()*1e6})
        )?)?;
    }
    binance.abort();
    feed.abort();
    logs.abort();
    output.write_all(&journal::frame(
        &json!({"kind":"summary","logs":count,"unmatched":pending.len()}),
    )?)?;
    output.flush()?;
    Ok(())
}
