mod block_quotes;
mod journal;
mod pool;
mod pyth;
mod relay;
mod snapshot;

use anyhow::{Context, Result, bail, ensure};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet, VecDeque},
    env,
    io::{self, BufRead, BufWriter, Write},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{
    sync::mpsc,
    time::{sleep, timeout},
};
use tokio_tungstenite::{connect_async, tungstenite::Message};

const POOL: &str = "0xa94e5130a57c48b0b2f266709634a45be7ae8171";
const PROVIDER: &str = "0x8a2414038ee7a77a3bb141f33ba2dc53e5ddfe50";
const SOURCE: &str = "0x0049bce28d8f04d51365cfafe2c87b1ad46873a0";
const ORACLE: &str = "0x30a88bf894d1b806125a23ebf23d715496fd7102";
const MULTIPLIER: &str = "0x6c38232b0597ef335bcdc86029cdc9e23a17f166";
const STOP_LOSS: &str = "0xe4038fa09f0bb9963068afaf97be0c045155090d";
const VELOCITY: &str = "0xebc53e61078976118e384f110c262a263decb84b";
const FEED_TOPIC: &str = "0x29e088dffd7bf6815d088137a59f364d6747163baa7ff4bc47f316a1ad1b9586";
const SPCX: &str = "0x0000000000000000000000000000000000000000000000000000000000000cf4";

fn now_ns() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}

fn quantity(value: &Value) -> Option<u64> {
    u64::from_str_radix(value.as_str()?.strip_prefix("0x")?, 16).ok()
}

fn write(out: &mut impl Write, record: &Value) -> Result<()> {
    serde_json::to_writer(&mut *out, record)?;
    writeln!(out)?;
    Ok(())
}

fn emit(queue: &mpsc::Sender<Value>, record: Value) -> Result<()> {
    queue.try_send(record).context("capture queue unavailable")
}

async fn socket(
    url: &str,
    chain: bool,
    endpoint: usize,
    queue: &mpsc::Sender<Value>,
    sequence: &mut u64,
    addresses: &[String],
) -> Result<()> {
    let (mut ws, _) = timeout(Duration::from_secs(10), connect_async(url)).await??;
    if chain {
        ws.send(Message::Text(
            json!({
                "jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]
            })
            .to_string()
            .into(),
        ))
        .await?;
        let response = timeout(Duration::from_secs(5), ws.next())
            .await?
            .context("missing chain ID")??;
        let chain_id: Value = serde_json::from_str(response.to_text()?)?;
        ensure!(
            quantity(&chain_id["result"]) == Some(4663),
            "unexpected chain ID"
        );
        for (id, params) in [
            (2, json!(["newHeads"])),
            (3, json!(["logs", {"address":addresses}])),
            (
                4,
                json!(["logs", {"address":ORACLE,"topics":[FEED_TOPIC,SPCX]}]),
            ),
        ] {
            ws.send(Message::Text(
                json!({
                    "jsonrpc":"2.0","id":id,"method":"eth_subscribe","params":params
                })
                .to_string()
                .into(),
            ))
            .await?;
        }
    }
    if !chain {
        emit(
            queue,
            json!({"kind":"connected","endpoint":endpoint,"recv_ns":now_ns()}),
        )?;
    }
    let mut subscriptions = std::collections::HashMap::new();
    loop {
        let frame = timeout(Duration::from_secs(if chain { 15 } else { 300 }), ws.next())
            .await?
            .context("socket ended")??;
        let recv_ns = now_ns();
        let Message::Text(text) = frame else {
            if matches!(frame, Message::Close(_)) {
                break;
            }
            if matches!(frame, Message::Ping(_)) {
                ws.flush().await?;
            }
            continue;
        };
        let message: Value = serde_json::from_str(&text)?;
        if !chain {
            let message = message.get("data").unwrap_or(&message);
            ensure!(
                message["s"].is_string() && message["u"].is_u64(),
                "invalid Binance BBO"
            );
            *sequence += 1;
            emit(
                queue,
                json!({"kind":"binance_bbo","tokyo_recv_ns":recv_ns,
                "relay_seq":*sequence,"ws_link":endpoint,"symbol":message["s"],"update_id":message["u"],"bid":message["b"],"bid_qty":message["B"],"ask":message["a"],"ask_qty":message["A"]}),
            )?;
            continue;
        }
        if let Some(id) = message["id"].as_u64() {
            let sub = message["result"]
                .as_str()
                .context("subscription rejected")?;
            subscriptions.insert(sub.to_owned(), id);
            if subscriptions.len() == 3 {
                emit(
                    queue,
                    json!({"kind":"connected","endpoint":endpoint,"recv_ns":recv_ns}),
                )?;
            }
            continue;
        }
        let params = &message["params"];
        let id = params["subscription"]
            .as_str()
            .and_then(|sub| subscriptions.get(sub));
        let kind = match id {
            Some(2) => "head",
            Some(3) => "contract_log",
            Some(4) => "oracle_log",
            _ => bail!("unknown subscription notification"),
        };
        emit(
            queue,
            json!({"kind":kind,"endpoint":endpoint,"recv_ns":recv_ns,
            "payload":params["result"]}),
        )?;
    }
    bail!("socket closed")
}

async fn reconnect(
    url: String,
    chain: bool,
    endpoint: usize,
    queue: mpsc::Sender<Value>,
    addresses: Vec<String>,
) {
    let mut sequence = 0;
    let mut delay_ms = 250;
    while !queue.is_closed() {
        let start = tokio::time::Instant::now();
        let err = socket(&url, chain, endpoint, &queue, &mut sequence, &addresses)
            .await
            .unwrap_err();
        // Transport errors can contain credential-bearing provider URLs.
        let reason = if err.to_string() == "capture queue unavailable" {
            "queue_overflow"
        } else {
            "socket_error"
        };
        if queue
            .send(json!({"kind":"gap","recv_ns":now_ns(),"endpoint":endpoint,"reason":reason}))
            .await
            .is_err()
        {
            break;
        }
        if start.elapsed() >= Duration::from_secs(30) {
            delay_ms = 250;
        }
        sleep(Duration::from_millis(delay_ms)).await;
        delay_ms = (delay_ms * 2).min(5000);
    }
}

async fn load_update(
    client: &reqwest::Client,
    rpc: &str,
    log: &Value,
) -> std::result::Result<Value, &'static str> {
    let hash = &log["transactionHash"];
    let response = client
        .post(rpc)
        .json(&json!({
            "jsonrpc":"2.0", "id":1, "method":"eth_getTransactionByHash","params":[hash]
        }))
        .send()
        .await
        .map_err(|err| {
            if err.is_timeout() {
                "http_timeout"
            } else {
                "http_transport"
            }
        })?;
    let response: Value = response
        .error_for_status()
        .map_err(|_| "http_status")?
        .json()
        .await
        .map_err(|err| {
            if err.is_timeout() {
                "http_timeout"
            } else {
                "invalid_rpc_json"
            }
        })?;
    decode_rpc_update(&response, log)
}

fn decode_rpc_update(response: &Value, log: &Value) -> std::result::Result<Value, &'static str> {
    if response["id"] != 1 || !response["error"].is_null() {
        return Err("rpc_error");
    }
    let tx = &response["result"];
    if tx.is_null() {
        return Err("transaction_unavailable");
    }
    if tx["hash"] != log["transactionHash"] || tx["blockHash"] != log["blockHash"] {
        return Err("transaction_block_mismatch");
    }
    if !tx["to"]
        .as_str()
        .is_some_and(|to| to.eq_ignore_ascii_case(ORACLE))
    {
        return Err("oracle_internal_call");
    }
    let input = tx["input"].as_str().ok_or("missing_input")?;
    let mut decoded = pyth::decode(input).map_err(|_| "unsupported_oracle_payload")?;
    decoded["relayer"] = tx["from"].clone();
    Ok(decoded)
}

async fn decode_updates(
    mut input: mpsc::Receiver<Value>,
    output: mpsc::Sender<Value>,
    rpc: String,
) -> Result<()> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_millis(750))
        .build()?;
    while let Some(record) = input.recv().await {
        let log = &record["payload"];
        let mut result = load_update(&client, &rpc, log).await;
        let mut failures = Vec::new();
        for delay_ms in [100, 250, 500] {
            let Err(reason) = result else { break };
            if matches!(
                reason,
                "oracle_internal_call" | "missing_input" | "unsupported_oracle_payload"
            ) {
                break;
            }
            failures.push(reason);
            sleep(Duration::from_millis(delay_ms)).await;
            result = load_update(&client, &rpc, log).await;
        }
        let decoded_ns = now_ns();
        let payload = match result {
            Ok(update) => json!({"kind":"oracle_update","recv_ns":record["recv_ns"],
                "decoded_ns":decoded_ns,"log":log,"update":update,"retry_errors":failures}),
            Err(reason) => {
                json!({"kind":"oracle_unresolved","recv_ns":record["recv_ns"],
                    "decoded_ns":decoded_ns,"log":log,"reason":reason,"retry_errors":failures})
            }
        };
        if output.send(payload).await.is_err() {
            break;
        }
    }
    Ok(())
}

fn swap_observation(log: &Value) -> Option<Value> {
    if log["topics"][0] != "0x9734819749a91fc3be03ea83205f924ee08479bd3f0da48efc91d94d050cac1e" {
        return None;
    }
    let data = hex::decode(log["data"].as_str()?.strip_prefix("0x")?).ok()?;
    if data.len() != 96 {
        return None;
    }
    let bin = i16::from_be_bytes(data[17..19].try_into().ok()?);
    let mut position = [0; 16];
    position[3..].copy_from_slice(&data[19..32]);
    let spcx = i128::from_be_bytes(data[32..48].try_into().ok()?);
    let usdg = i128::from_be_bytes(data[48..64].try_into().ok()?);
    Some(json!({
        "active_bin":bin,
        "position_in_bin":u128::from_be_bytes(position).to_string(),
        "delta0_raw":spcx.to_string(),
        "delta1_raw":usdg.to_string()
    }))
}

#[derive(Default)]
struct Observations {
    recent: HashSet<Value>,
    order: VecDeque<Value>,
    oracle: Option<(u64, Value)>,
    head_time: Option<u64>,
    invalidated_at_ns: u64,
}

impl Observations {
    fn duplicate(&mut self, record: &Value) -> bool {
        let item = &record["payload"];
        let key = match record["kind"].as_str() {
            Some("head") => json!(["head", item["hash"]]),
            Some("contract_log" | "oracle_log") => {
                json!([item["blockHash"], item["logIndex"], item["removed"]])
            }
            _ => return false,
        };
        if !self.recent.insert(key.clone()) {
            return true;
        }
        self.order.push_back(key);
        if self.order.len() > 32768 {
            self.recent.remove(&self.order.pop_front().unwrap());
        }
        false
    }

    fn apply(&mut self, record: &mut Value) {
        match record["kind"].as_str() {
            Some("head") => {
                if let Some(time) = quantity(&record["payload"]["timestamp"]) {
                    self.head_time = Some(self.head_time.map_or(time, |old| old.max(time)));
                }
            }
            Some("oracle_update") => {
                if record["recv_ns"].as_u64().unwrap_or_default() <= self.invalidated_at_ns {
                    return;
                }
                let publish = record["update"]["publish_us"].as_u64().unwrap();
                if self.oracle.as_ref().is_none_or(|(old, _)| publish > *old) {
                    self.oracle = Some((publish, record["update"].clone()));
                }
            }
            Some("gap" | "oracle_unresolved") => {
                self.oracle = None;
                self.invalidated_at_ns = now_ns();
            }
            Some("oracle_log") if record["payload"]["removed"] == true => {
                self.oracle = None;
                self.invalidated_at_ns = now_ns();
            }
            _ => return,
        }
        if let (Some(time), Some((publish, update))) = (self.head_time, &self.oracle) {
            let age = i128::from(time) - i128::from(publish / 1_000_000);
            record["observed_oracle"] = json!({
                "price_e8":update["price_e8"],"publish_us":publish,
                "age_s":age as i64,"fresh":(0..=15).contains(&age)
            });
        }
    }
}

fn universe() -> Result<(HashSet<String>, Vec<String>)> {
    let catalog: Value =
        serde_json::from_str(include_str!("../reports/metric-pools-over-10k.json"))?;
    let mut pools = HashSet::new();
    let mut addresses = HashSet::new();
    for row in catalog["pools"]
        .as_array()
        .context("missing pool catalog")?
    {
        if row["chain_id"] != 4663 {
            continue;
        }
        let address = row["pool"]
            .as_str()
            .context("missing pool address")?
            .to_ascii_lowercase();
        pools.insert(address.clone());
        addresses.insert(address);
        for key in ["provider", "source"] {
            if let Some(address) = row[key].as_str()
                && address != "0x0000000000000000000000000000000000000000"
            {
                addresses.insert(address.to_ascii_lowercase());
            }
        }
    }
    ensure!(pools.contains(POOL), "catalog missing Carcosa SPCX");
    addresses.extend([PROVIDER, SOURCE, MULTIPLIER, STOP_LOSS, VELOCITY].map(str::to_owned));
    let mut addresses: Vec<_> = addresses.into_iter().collect();
    addresses.sort_unstable();
    Ok((pools, addresses))
}

fn compact_log(log: &Value) -> Value {
    json!({"address":log["address"],"block":quantity(&log["blockNumber"]),
        "block_hash":log["blockHash"],"tx":log["transactionHash"],
        "tx_index":quantity(&log["transactionIndex"]),"log_index":quantity(&log["logIndex"]),
        "removed":log["removed"]})
}

fn compact(record: &mut Value, pools: &HashSet<String>) -> Result<()> {
    match record["kind"].as_str() {
        Some("head") => {
            let head = record.as_object_mut().unwrap().remove("payload").unwrap();
            record["block"] = json!(quantity(&head["number"]));
            record["block_time_s"] = json!(quantity(&head["timestamp"]));
            record["hash"] = head["hash"].clone();
            record["parent"] = head["parentHash"].clone();
        }
        Some("contract_log" | "oracle_log") => {
            let log = record.as_object_mut().unwrap().remove("payload").unwrap();
            record["log"] = compact_log(&log);
            let is_pool = log["address"]
                .as_str()
                .is_some_and(|a| pools.contains(&a.to_ascii_lowercase()));
            if record["kind"] == "oracle_log" {
                record["feed_id"] = json!(pyth::FEED);
            } else if let Some(event) = is_pool.then(|| pool::decode(&log)).transpose()?.flatten() {
                record["kind"] = json!("pool_update");
                record["change"] = event;
            } else if let Some(swap) = is_pool.then(|| swap_observation(&log)).flatten() {
                record["kind"] = json!("swap");
                record["swap"] = swap;
            } else {
                record["topics"] = log["topics"].clone();
                record["data"] = log["data"].clone();
            }
        }
        Some("oracle_update" | "oracle_unresolved") => {
            record["log"] = compact_log(&record["log"]);
        }
        _ => {}
    }
    Ok(())
}

/// Apply commutative balance deltas while tracking gaps. The capture starts without an anchor.
fn track_bins(
    record: &mut Value,
    bins: &mut HashMap<String, pool::Bins>,
    anchors: &HashMap<String, u64>,
    epoch: &mut u64,
) -> Result<()> {
    if record["kind"] == "gap" || record["log"]["removed"] == true {
        bins.clear();
        *epoch += 1;
    }
    if record["kind"] == "pool_update" && record["log"]["removed"] != true {
        let address = record["log"]["address"]
            .as_str()
            .context("missing pool address")?;
        let address = address.to_ascii_lowercase();
        let block = record["log"]["block"]
            .as_u64()
            .context("missing event block")?;
        let anchor = anchors.get(&address);
        if anchor.is_none_or(|height| block > *height) {
            bins.entry(address).or_default().apply(&record["change"])?;
        }
        record["bin_anchor"] = json!(anchor);
        record["bin_epoch"] = json!(*epoch);
    }
    Ok(())
}

async fn capture(chain: bool) -> Result<()> {
    let (pools, addresses) = if chain {
        universe()?
    } else {
        (HashSet::new(), Vec::new())
    };
    let (send, mut receive) = mpsc::channel(8192);
    let (quote_tx, quote_rx) = mpsc::channel(8192);
    let (decode_tx, decode_rx) = mpsc::channel(512);
    let mut urls = list_env("BINANCE_WS_URLS");
    if urls.is_empty() && !chain {
        let mut symbols = list_env("BINANCE_SYMBOLS");
        if symbols.is_empty() {
            symbols = "ETHUSDT,SPCXBUSDT,METABUSDT,TSLABUSDT,GOOGLBUSDT,NVDABUSDT,AAPLBUSDT,MUBUSDT,SPYBUSDT,QQQBUSDT,INTCBUSDT"
                .split(',').map(str::to_owned).collect();
        }
        let streams = symbols
            .iter()
            .map(|symbol| format!("{}@bookTicker", symbol.to_ascii_lowercase()))
            .collect::<Vec<_>>()
            .join("/");
        urls = [
            "stream.binance.com",
            "data-stream.binance.vision",
            "stream.binance.com",
        ]
        .map(|host| format!("wss://{host}:443/stream?streams={streams}"))
        .to_vec();
    }
    let mut snapshot_rpc = None;
    let relay_sender = if chain {
        None
    } else {
        Some(relay::sender(&list_env("BINANCE_LISTEN")).await?)
    };
    if chain {
        urls = env::var("ROBIN_WS_URLS")
            .context("set ROBIN_WS_URLS")?
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
            .collect();
        ensure!(!urls.is_empty(), "missing Robinhood WS URL");
        let quote_url = env::var("ROBIN_QUOTE_WS_URL").unwrap_or_else(|_| urls[0].clone());
        tokio::spawn(block_quotes::run(quote_rx, send.clone(), quote_url));
        if let Ok(rpc) = env::var("ROBIN_RPC_URL") {
            tokio::spawn(decode_updates(decode_rx, send.clone(), rpc.clone()));
            if env::var_os("ROBIN_NO_ETH_CALL").is_none() {
                snapshot_rpc = Some(rpc.clone());
            }
        }
    }
    for (endpoint, url) in urls.into_iter().enumerate() {
        tokio::spawn(reconnect(
            url,
            chain,
            endpoint,
            send.clone(),
            addresses.clone(),
        ));
    }
    if chain {
        for (link, address) in list_env("BINANCE_RELAY_ADDRS").into_iter().enumerate() {
            tokio::spawn(relay::receive(address, link, send.clone()));
        }
    }
    let mut snapshot_tick = tokio::time::interval(Duration::from_secs(
        env::var("ROBIN_SYNC_SECS")
            .ok()
            .and_then(|s| s.parse().ok())
            .filter(|n| *n > 0)
            .unwrap_or(300),
    ));
    snapshot_tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    let mut state = Observations::default();
    let mut bins = HashMap::new();
    let mut epoch = 0;
    let mut binance_ids = relay::Dedup::default();
    let mut snapshot_in_flight = false;
    let mut sync_needed = false;
    let mut chain_ready = false;
    let mut changes = VecDeque::new();
    let mut anchors = HashMap::new();
    let mut stdout = BufWriter::with_capacity(256 * 1024, io::stdout().lock());
    stdout.write_all(journal::MAGIC)?;
    stdout.write_all(&journal::frame(&json!({"kind":"capture_start","schema":3,
        "recv_ns":now_ns(),"pool_count":pools.len(),"bin_state":"pending"}))?)?;
    let mut flush = tokio::time::interval(Duration::from_millis(250));
    let duration = env::var("CAPTURE_SECS")
        .ok()
        .map(|s| s.parse::<u64>())
        .transpose()?;
    let deadline = tokio::time::sleep(Duration::from_secs(duration.unwrap_or(31_536_000)));
    tokio::pin!(deadline);
    let shutdown = tokio::signal::ctrl_c();
    tokio::pin!(shutdown);
    loop {
        if sync_needed
            && !snapshot_in_flight
            && let Some(rpc) = &snapshot_rpc
        {
            sync_needed = false;
            snapshot_in_flight = true;
            let (rpc, pools, send) = (rpc.clone(), pools.iter().cloned().collect(), send.clone());
            tokio::spawn(async move {
                let record = snapshot::read(&rpc, pools, epoch).await.unwrap_or_else(
                    |_| json!({"kind":"bin_snapshot_failed","bin_epoch":epoch,"recv_ns":now_ns()}),
                );
                let _ = send.send(record).await;
            });
        }
        let mut record = tokio::select! {
            item = receive.recv() => item.context("closed capture channel")?,
            _ = flush.tick() => { stdout.flush()?; continue; }
            _ = snapshot_tick.tick(), if chain => { if chain_ready && !snapshot_in_flight { sync_needed = true; } continue; }
            _ = &mut deadline => break,
            result = &mut shutdown => { result?; break; }
        };
        if record["kind"] == "binance_bbo" && !binance_ids.first(&record) {
            continue;
        }
        if state.duplicate(&record) {
            continue;
        }
        if !decode_tx.is_closed()
            && record["kind"] == "oracle_log"
            && record["payload"]["removed"] != true
        {
            decode_tx
                .try_send(record.clone())
                .context("oracle decoder queue unavailable")?;
        }
        if record["kind"] == "head" && !quote_tx.is_closed() {
            quote_tx
                .try_send(record.clone())
                .context("block quote queue unavailable")?;
        }
        state.apply(&mut record);
        compact(&mut record, &pools)?;
        if record["kind"] == "bin_snapshot" || record["kind"] == "bin_snapshot_failed" {
            snapshot_in_flight = false;
        }
        if record["kind"] == "bin_snapshot" && record["bin_epoch"] == epoch {
            install_snapshot(&mut record, &mut bins, &mut anchors, &mut changes)?;
        } else if record["kind"] == "bin_snapshot" {
            record["discarded"] = json!(true);
        }
        if record["kind"] == "connected" && chain {
            chain_ready = true;
            sync_needed = true;
        }
        if record["kind"] == "gap" || record["log"]["removed"] == true {
            anchors.clear();
            changes.clear();
            sync_needed = chain_ready && record["log"]["removed"] == true;
        }
        if record["kind"] == "pool_update" && record["log"]["removed"] != true {
            changes.push_back(record.clone());
            if changes.len() > 262_144 {
                changes.clear();
                anchors.clear();
                bins.clear();
                epoch += 1;
                sync_needed = true;
                record["gap"] = json!("bin_history_overflow");
            }
        }
        track_bins(&mut record, &mut bins, &anchors, &mut epoch)?;
        let frame = journal::frame(&record)?;
        if record["kind"] == "binance_bbo"
            && let Some(relay) = &relay_sender
        {
            let _ = relay.send(frame.clone());
        }
        stdout.write_all(&frame)?;
    }
    stdout.flush()?;
    Ok(())
}

fn list_env(key: &str) -> Vec<String> {
    env::var(key)
        .unwrap_or_default()
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect()
}

fn install_snapshot(
    record: &mut Value,
    bins: &mut HashMap<String, pool::Bins>,
    anchors: &mut HashMap<String, u64>,
    changes: &mut VecDeque<Value>,
) -> Result<()> {
    let height = record["block"]
        .as_u64()
        .context("missing snapshot height")?;
    let mut mismatches = 0;
    let mut compared = 0;
    for row in record["pools"]
        .as_array()
        .context("missing pool snapshots")?
    {
        let address = row["pool"].as_str().context("missing snapshot address")?;
        let mut snapshot = pool::Bins::default();
        snapshot.apply(row)?;
        if let Some(anchor) = anchors.get(address).filter(|anchor| **anchor <= height) {
            // Undo observations newer than this block before comparing with the checkpoint.
            let mut candidate = bins.get(address).context("missing anchored bins")?.clone();
            for event in changes.iter().filter(|e| {
                e["log"]["address"]
                    .as_str()
                    .is_some_and(|x| x.eq_ignore_ascii_case(address))
                    && e["log"]["block"]
                        .as_u64()
                        .is_some_and(|b| b > height && b > *anchor)
            }) {
                candidate.apply_signed(&event["change"], -1)?;
            }
            compared += 1;
            mismatches += usize::from(candidate.balances != snapshot.balances);
        }
        for event in changes.iter().filter(|e| {
            e["log"]["address"]
                .as_str()
                .is_some_and(|x| x.eq_ignore_ascii_case(address))
                && e["log"]["block"].as_u64().is_some_and(|b| b > height)
        }) {
            snapshot.apply(&event["change"])?;
        }
        bins.insert(address.to_owned(), snapshot);
        anchors.insert(address.to_owned(), height);
    }
    let oldest = anchors.values().copied().min().unwrap_or(0);
    changes.retain(|event| event["log"]["block"].as_u64().is_some_and(|b| b > oldest));
    record["compared"] = json!(compared);
    record["mismatches"] = json!(mismatches);
    Ok(())
}

fn receive_relay() -> Result<()> {
    let mut out = io::stdout().lock();
    for line in io::stdin().lock().lines() {
        let recv_ns = now_ns();
        let mut row: Value = serde_json::from_str(&line?)?;
        ensure!(row.is_object(), "invalid relay row");
        row["ohio_recv_ns"] = json!(recv_ns);
        write(&mut out, &row)?;
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    match env::args().nth(1).as_deref() {
        Some("ohio") => capture(true).await,
        Some("tokyo") => capture(false).await,
        Some("relay-receive") => receive_relay(),
        Some("replay") => {
            let file = env::args()
                .nth(2)
                .context("usage: robin-leadlag replay <file|->")?;
            let output = BufWriter::new(io::stdout().lock());
            if file == "-" {
                journal::replay(io::stdin().lock(), output)
            } else {
                journal::replay(io::BufReader::new(std::fs::File::open(file)?), output)
            }
        }
        Some("decode-pyth") => {
            let input = io::stdin()
                .lock()
                .lines()
                .next()
                .context("missing input")??;
            write(&mut io::stdout().lock(), &pyth::decode(&input)?)
        }
        _ => bail!("usage: robin-leadlag <ohio|tokyo|relay-receive|decode-pyth>"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distinguishes_unindexed_tx_from_valid_update() {
        let tx: Value = json!({
            "hash": "0x810af7b6ca55664d11865833ce1dfe64d86b6548ed941f203f14f1674aa2042f",
            "blockHash": "0x94b086024995ea0744e1c1689828f8440f564190f2d81944ef71955ed8db7a08",
            "to": ORACLE,
            "input": include_str!("../tests/fixtures/spcx-late-tx.hex").trim()
        });
        let log = json!({"transactionHash":tx["hash"],"blockHash":tx["blockHash"]});
        assert_eq!(
            decode_rpc_update(&json!({"id":1,"result":null}), &log),
            Err("transaction_unavailable")
        );
        let update = decode_rpc_update(&json!({"id":1,"result":tx}), &log).unwrap();
        assert_eq!(update["price_e8"], 13_604_062_000u64);
        assert_eq!(update["spread_e6"], 1);
        assert_eq!(update["publish_us"], 1_794_658_537_200_000u64);
    }
}
