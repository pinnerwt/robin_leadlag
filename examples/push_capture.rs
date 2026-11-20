//! Push-only raw capture. No chain reads, historical recovery or quote claims.
#[allow(dead_code)]
#[path = "../src/journal.rs"]
mod journal;
use anyhow::{Context, Result, ensure};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet, VecDeque},
    io::{self, BufWriter, Write},
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use tokio::{
    sync::mpsc,
    time::{Duration, timeout},
};
use tokio_tungstenite::{
    connect_async,
    tungstenite::{Message, client::IntoClientRequest},
};

#[derive(Clone, Copy)]
struct Clock {
    start: Instant,
    utc: u64,
}
impl Clock {
    fn stamp(self, row: &mut Value) {
        row["mono_ns"] = json!(self.start.elapsed().as_nanos() as u64);
        row["recv_ns"] = json!(
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos() as u64
        );
    }
}
fn emit(out: &mpsc::Sender<Value>, row: Value) -> Result<()> {
    out.try_send(row)
        .context("capture queue full or closed; terminating to avoid silent loss")
}
// Subscription progress is independent of transport liveness: heads/pings must
// not hide a stopped logs subscription. Empty blocks alone do not expect logs.
struct ProgressWatch {
    head: Instant,
    data: Instant,
    awaiting_logs: Option<Instant>,
    logged_blocks: HashSet<String>,
    log_order: VecDeque<String>,
}
impl ProgressWatch {
    fn new(now: Instant) -> Self { Self { head: now, data: now, awaiting_logs: None, logged_blocks: HashSet::new(), log_order: VecDeque::new() } }
    fn head(&mut self, now: Instant, bloom: Option<&str>, hash: Option<&str>) {
        self.head = now;
        if hash.is_some_and(|h| self.logged_blocks.contains(h)) { return; }
        if bloom.is_some_and(|b| b.trim_start_matches("0x").bytes().any(|v| v != b'0')) {
            self.awaiting_logs.get_or_insert(now);
        }
    }
    fn log(&mut self, hash: Option<&str>) {
        self.awaiting_logs = None;
        if let Some(h) = hash {
            if self.logged_blocks.insert(h.to_owned()) { self.log_order.push_back(h.to_owned()); }
            while self.log_order.len() > 2048 {
                if let Some(old) = self.log_order.pop_front() { self.logged_blocks.remove(&old); }
            }
        }
    }
    fn stalled(&self, now: Instant, limit: Duration, chain: bool) -> bool {
        if chain { now.duration_since(self.head) >= limit || self.awaiting_logs.is_some_and(|t| now.duration_since(t) >= limit) }
        else { now.duration_since(self.data) >= limit }
    }
}
async fn socket(
    kind: &str,
    url: &str,
    link: usize,
    epoch: u64,
    clock: Clock,
    out: &mpsc::Sender<Value>,
    progress_timeout: Duration,
) -> Result<()> {
    let mut request = url.into_client_request()?;
    if kind == "nitro" {
        request
            .headers_mut()
            .insert("arbitrum-feed-client-version", "2".parse()?);
    }
    let (mut ws, _) = timeout(Duration::from_secs(15), connect_async(request)).await??;
    let mut connected = json!({"kind":"connected","stream":kind,"link":link,"epoch":epoch});
    clock.stamp(&mut connected);
    emit(out, connected)?;
    if kind == "chain" {
        for (id, params) in [(1, json!(["logs", {}])), (2, json!(["newHeads"]))] {
            ws.send(Message::Text(
                json!({"jsonrpc":"2.0","id":id,"method":"eth_subscribe","params":params})
                    .to_string()
                    .into(),
            ))
            .await?;
        }
    }
    let mut subscriptions = HashMap::new();
    let mut progress = ProgressWatch::new(Instant::now());
    loop {
        ensure!(!progress.stalled(Instant::now(), progress_timeout, kind == "chain"), "subscription progress stalled");
        let frame = match timeout(Duration::from_secs(1), ws.next()).await {
            Err(_) => continue,
            Ok(frame) => frame.context("closed")??,
        };
        // Stamp before parsing or queueing. Wall clock and monotonic clock are both retained.
        let mut record = json!({"link":link,"epoch":epoch});
        clock.stamp(&mut record);
        match frame {
            Message::Text(text) => {
                let row: Value = serde_json::from_str(&text)?;
                ensure!(row["error"].is_null(), "subscription rejected");
                match kind {
                    "nitro" => {
                        record["kind"] = json!("nitro_push");
                        if let Some(raw) = row["raw"].as_str() {
                            record["relay_recv_ns"] = row["relay_recv_ns"].clone();
                            record["relay_mono_ns"] = row["relay_mono_ns"].clone();
                            record["payload"] = serde_json::from_str(raw)?;
                        } else {
                            record["payload"] = row;
                        }
                    }
                    "binance" => {
                        let row = row.get("data").unwrap_or(&row);
                        ensure!(
                            row["s"].is_string()
                                && row["u"].is_u64()
                                && row["b"].is_string()
                                && row["a"].is_string(),
                            "invalid BBO"
                        );
                        record["kind"] = json!("bbo");
                        for (key, field) in [
                            ("symbol", "s"),
                            ("update_id", "u"),
                            ("bid", "b"),
                            ("ask", "a"),
                            ("bid_qty", "B"),
                            ("ask_qty", "A"),
                        ] {
                            record[key] = row[field].clone();
                        }
                    }
                    "chain" => {
                        if let Some(id) = row["id"].as_u64() {
                            let sub = row["result"]
                                .as_str()
                                .context("subscription not acknowledged")?;
                            ensure!(id == 1 || id == 2, "unexpected subscription id");
                            subscriptions.insert(sub.to_owned(), id);
                            record["kind"] = json!("subscribed");
                            record["subscription_kind"] =
                                json!(if id == 1 { "logs" } else { "heads" });
                        } else {
                            let sub = row["params"]["subscription"]
                                .as_str()
                                .context("missing subscription")?;
                            let id = subscriptions.get(sub).context("unknown subscription")?;
                            record["kind"] = json!(if *id == 1 { "chain_log" } else { "head" });
                            record["payload"] = row["params"]["result"].clone();
                        }
                    }
                    _ => unreachable!(),
                }
                if kind == "chain" {
                    if record["kind"] == "head" { progress.head(Instant::now(), record["payload"]["logsBloom"].as_str(), record["payload"]["hash"].as_str()); }
                    if record["kind"] == "chain_log" { progress.log(record["payload"]["blockHash"].as_str()); }
                } else { progress.data = Instant::now(); }
                emit(out, record)?;
            }
            Message::Ping(_) => ws.flush().await?,
            Message::Close(_) => anyhow::bail!("closed"),
            _ => {}
        }
    }
}
async fn reconnect(
    kind: &'static str,
    url: String,
    link: usize,
    clock: Clock,
    out: mpsc::Sender<Value>,
    progress_timeout: Duration,
) -> Result<()> {
    let mut epoch = 0;
    loop {
        // Deliberately redact transport errors: URLs can carry credentials.
        let result = socket(kind, &url, link, epoch, clock, &out, progress_timeout).await;
        let mut row = json!({"kind":"gap","stream":kind,"link":link,"epoch":epoch,"reason":if result.is_err(){"transport_or_decode_error"}else{"closed"},"state_valid":false});
        clock.stamp(&mut row);
        emit(&out, row)?;
        epoch += 1;
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
}
fn accept_bbo(row: &Value, last: &mut HashMap<String, u64>) -> Result<bool> {
    let symbol = row["symbol"].as_str().context("missing symbol")?;
    let id = row["update_id"].as_u64().context("missing update ID")?;
    if last.get(symbol).is_some_and(|old| id <= *old) {
        return Ok(false);
    }
    last.insert(symbol.to_owned(), id);
    Ok(true)
}
#[tokio::main]
async fn main() -> Result<()> {
    let path = std::env::args()
        .nth(1)
        .context("usage: push_capture config.json [seconds]")?;
    let config: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let duration = std::env::args()
        .nth(2)
        .map(|v| v.parse())
        .transpose()?
        .unwrap_or(config["duration_secs"].as_u64().context("duration_secs")?);
    let symbols: Vec<String> = config["symbols"]
        .as_array()
        .context("symbols")?
        .iter()
        .map(|v| Ok(v.as_str().context("symbol")?.to_owned()))
        .collect::<Result<_>>()?;
    ensure!(!symbols.is_empty(), "empty symbols");
    let streams = symbols
        .iter()
        .map(|s| format!("{}@bookTicker", s.to_lowercase()))
        .collect::<Vec<_>>()
        .join("/");
    let binance_url = format!(
        "{}{}",
        config["binance_base"].as_str().context("binance_base")?,
        streams
    );
    let clock = Clock {
        start: Instant::now(),
        utc: SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos() as u64,
    };
    let (out, mut input) = mpsc::channel(65536);
    let mut tasks = tokio::task::JoinSet::new();
    let progress_seconds = config["subscription_progress_timeout_seconds"].as_u64().unwrap_or(30);
    ensure!((5..=300).contains(&progress_seconds), "invalid progress timeout");
    let progress_timeout = Duration::from_secs(progress_seconds);
    for (kind, key) in [("nitro", "feed_url"), ("chain", "logs_url")] {
        tasks.spawn(reconnect(
            kind,
            config[key].as_str().with_context(|| key)?.to_owned(),
            0,
            clock,
            out.clone(),
            progress_timeout,
        ));
    }
    let links = config["binance_connections"]
        .as_u64()
        .context("binance_connections")?;
    ensure!((0..=16).contains(&links), "invalid connection count");
    for link in 0..links {
        tasks.spawn(reconnect(
            "binance",
            binance_url.clone(),
            link as usize,
            clock,
            out.clone(),
            progress_timeout,
        ));
    }
    drop(out);
    // Dedicated blocking writer: disk/pipe backpressure never blocks a websocket reader.
    let (disk_tx, disk_rx) = std::sync::mpsc::sync_channel::<Vec<u8>>(65536);
    let writer = std::thread::spawn(move || -> Result<()> {
        let mut output = BufWriter::with_capacity(256 * 1024, io::stdout().lock());
        output.write_all(journal::MAGIC)?;
        while let Ok(frame) = disk_rx.recv() {
            output.write_all(&frame)?;
        }
        output.flush()?;
        Ok(())
    });
    let write = |v: &Value| -> Result<()> {
        disk_tx
            .try_send(journal::frame(v)?)
            .context("disk queue unavailable")
    };
    write(
        &json!({"kind":"session","start_utc_ns":clock.utc,"symbols":symbols,"pools":config["pools"],"catalog_asof":config["catalog_asof"],"state_valid":false,"reason":"no_verified_initial_state","requests":"eth_subscribe_only","binance_connections":links,"binance_enabled":links>0}),
    )?;
    let stop = tokio::time::sleep(Duration::from_secs(duration));
    tokio::pin!(stop);
    let mut stats = tokio::time::interval(Duration::from_secs(10));
    let mut last = HashMap::new();
    let mut counts = HashMap::<String, u64>::new();
    let mut duplicates = 0u64;
    let mut failure = None;
    loop {
        tokio::select! {
            _=&mut stop => break,
            _=tokio::signal::ctrl_c() => break,
            task=tasks.join_next() => {failure=Some(format!("receiver terminated: {task:?}"));break;},
            _=stats.tick() => {
                let missing:Vec<_>=symbols.iter().filter(|s|links>0&&!last.contains_key(*s)).collect();
                let mut row=json!({"kind":"coverage","counts":counts,"symbols_seen":last.keys().collect::<Vec<_>>(),"missing_symbols":missing,"duplicates":duplicates});clock.stamp(&mut row);
                eprintln!("{}",row);if let Err(e)=write(&row){failure=Some(e.to_string());break;}
            },
            row=input.recv() => {
                let Some(row)=row else {failure=Some("receivers closed".into());break;};
                if row["kind"]=="bbo" && !accept_bbo(&row,&mut last)? {duplicates+=1;continue;}
                *counts.entry(row["kind"].as_str().unwrap().to_owned()).or_default()+=1;
                if let Err(e)=write(&row){failure=Some(e.to_string());break;}
            }
        }
    }
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    while let Ok(row) = input.try_recv() {
        if row["kind"] == "bbo" && !accept_bbo(&row, &mut last)? {
            continue;
        }
        if write(&row).is_err() {
            failure = Some("disk queue unavailable while draining".into());
            break;
        }
    }
    let final_row = json!({"kind":"capture_end","complete":failure.is_none(),"failure":failure,"counts":counts,"state_valid":false});
    // Blocking only after readers have stopped; ensures a durable end marker when possible.
    disk_tx
        .send(journal::frame(&final_row)?)
        .context("writer ended")?;
    drop(disk_tx);
    writer
        .join()
        .map_err(|_| anyhow::anyhow!("writer panicked"))??;
    ensure!(failure.is_none(), "capture failed: {:?}", failure);
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn logs_before_header_do_not_mark_a_quiet_chain_stalled() {
        let t=Instant::now();let mut p=ProgressWatch::new(t);let limit=Duration::from_secs(10);
        p.log(Some("block"));p.head(t,Some("0x01"),Some("block"));
        p.head(t+limit,Some("0x0000"),Some("empty"));
        assert!(!p.stalled(t+limit,limit,true));
    }
    #[test]
    fn head_traffic_does_not_mask_missing_logs() {
        let t=Instant::now();let mut p=ProgressWatch::new(t);let limit=Duration::from_secs(10);
        p.head(t,Some("0x01"),None);p.head(t+Duration::from_secs(9),Some("0x01"),None);
        assert!(p.stalled(t+limit,limit,true));
        p.log(None);assert!(!p.stalled(t+limit,limit,true));
    }
    #[test]
    fn empty_blocks_are_not_a_logs_failure_and_pings_cannot_refresh_heads() {
        let t=Instant::now();let mut p=ProgressWatch::new(t);let limit=Duration::from_secs(10);
        p.head(t+limit,Some("0x0000"),None);assert!(!p.stalled(t+limit,limit,true));
        assert!(p.stalled(t+limit+limit,limit,true));
        assert!(p.stalled(t+limit,limit,false));
    }
    #[test]
    fn symbol_scoped_highwater_drops_duplicates_and_late_copies() {
        let mut last = HashMap::new();
        for (s, id, expected) in [
            ("A", 10, true),
            ("A", 10, false),
            ("A", 9, false),
            ("B", 9, true),
            ("A", 11, true),
        ] {
            assert_eq!(
                accept_bbo(&json!({"symbol":s,"update_id":id}), &mut last).unwrap(),
                expected
            );
        }
    }
}
