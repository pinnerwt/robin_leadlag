use anyhow::{Context, Result, ensure};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use sha3::{Digest, Keccak256};
use tokio::net::TcpStream;
use tokio::sync::mpsc;
use tokio::time::{Duration, timeout};
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream, connect_async, tungstenite::Message};

const ORACLE: &str = "0xe844701934d9c6085b292e428f41b911cc0b3872";
const FEED: &str = "0x8dfdc825dd0453e7c80b1c1d32ae910e35d6efe9000000000000000012375400";
const POOL: &str = "0xa94e5130a57c48b0b2f266709634a45be7ae8171";
const Q64: u128 = 1 << 64;

#[derive(Clone, Copy)]
struct Source {
    time_ms: u64,
    price: u128,
    bid_spread: u128,
    ask_spread: u128,
    stalled: bool,
}

impl Source {
    fn decode(input: &str, codebook: &[u16]) -> Result<Self> {
        let bytes = hex::decode(input.strip_prefix("0x").context("invalid calldata")?)?;
        ensure!(
            bytes.len() > 1 && (bytes.len() - 1) % 32 == 0,
            "unexpected push format"
        );
        let slot = bytes[1..]
            .chunks_exact(32)
            .filter(|w| w[31] == 0x54)
            .max_by_key(|w| &w[24..31])
            .context("SPCX slot missing")?;
        let packed = u32::from_be_bytes(slot[..4].try_into()?);
        let mut time = [0; 8];
        time[1..].copy_from_slice(&slot[24..31]);
        Ok(Self {
            time_ms: u64::from_be_bytes(time),
            price: u128::from(packed & ((1 << 27) - 1)) << (packed >> 27),
            bid_spread: codebook[slot[4] as usize].into(),
            ask_spread: codebook[slot[5] as usize].into(),
            stalled: slot[4..6] == [255, 255],
        })
    }

    fn edges(self) -> (u128, u128) {
        let mid = self.price * Q64;
        (
            mid * (1_000_000 - self.bid_spread) / 10_u128.pow(14),
            (mid * (1_000_000 + self.ask_spread)).div_ceil(10_u128.pow(14)),
        )
    }
}

fn bloom_has(bloom: &[u8], token: &str) -> Result<bool> {
    ensure!(bloom.len() == 256, "invalid header bloom");
    let hash = Keccak256::digest(hex::decode(&token[2..])?);
    Ok(hash[..6].chunks_exact(2).all(|chunk| {
        let bit = ((usize::from(chunk[0]) << 8) | usize::from(chunk[1])) & 2047;
        bloom[255 - bit / 8] & (1 << (bit % 8)) != 0
    }))
}

struct Rpc {
    url: String,
    ws: Option<WebSocketStream<MaybeTlsStream<TcpStream>>>,
    id: u64,
}

impl Rpc {
    async fn request(&mut self, method: &str, params: Value) -> Result<Value> {
        let result = timeout(Duration::from_secs(2), self.exchange(method, params)).await;
        if !matches!(&result, Ok(Ok(_))) {
            self.ws = None;
        }
        result?
    }

    async fn exchange(&mut self, method: &str, params: Value) -> Result<Value> {
        if self.ws.is_none() {
            self.ws = Some(connect_async(&self.url).await?.0);
        }
        let ws = self.ws.as_mut().unwrap();
        self.id += 1;
        let id = self.id;
        ws.send(Message::Text(
            json!({"jsonrpc":"2.0","id":id,
            "method":method,"params":params})
            .to_string()
            .into(),
        ))
        .await?;
        while let Some(frame) = ws.next().await {
            match frame? {
                Message::Text(text) => {
                    let response: Value = serde_json::from_str(&text)?;
                    ensure!(
                        response["id"] == id
                            && response["error"].is_null()
                            && !response["result"].is_null(),
                        "missing or mismatched WS RPC result"
                    );
                    return Ok(response["result"].clone());
                }
                Message::Ping(_) => ws.flush().await?,
                Message::Close(_) => break,
                _ => {}
            }
        }
        anyhow::bail!("quote RPC socket closed")
    }
}

async fn update(
    rpc: &mut Rpc,
    hash: &Value,
    bloom: &[u8],
    oracle: &str,
    feed: &str,
) -> Result<Option<Value>> {
    if !bloom_has(bloom, oracle)?
        || !bloom_has(bloom, feed)?
        || !bloom_has(bloom, super::FEED_TOPIC)?
    {
        return Ok(None);
    }
    let logs = rpc
        .request(
            "eth_getLogs",
            json!([{"blockHash":hash,"address":oracle,
        "topics":[super::FEED_TOPIC,feed]}]),
        )
        .await?;
    let logs = logs.as_array().context("invalid logs response")?;
    // A bloom false positive is legal. Validate identity and sort by execution order.
    let mut latest = None;
    for log in logs {
        ensure!(
            log["blockHash"] == *hash
                && log["removed"] == false
                && log["address"]
                    .as_str()
                    .is_some_and(|s| s.eq_ignore_ascii_case(oracle))
                && log["topics"] == json!([super::FEED_TOPIC, feed]),
            "wrong update log"
        );
        let index = super::quantity(&log["logIndex"]).context("missing log index")?;
        if latest.is_none_or(|(old, _)| index > old) {
            latest = Some((index, log));
        }
    }
    let Some((_, log)) = latest else {
        return Ok(None);
    };
    let tx = rpc
        .request("eth_getTransactionByHash", json!([log["transactionHash"]]))
        .await?;
    ensure!(
        tx["blockHash"] == *hash
            && tx["hash"] == log["transactionHash"]
            && tx["to"]
                .as_str()
                .is_some_and(|s| s.eq_ignore_ascii_case(oracle)),
        "unmatched update transaction"
    );
    Ok(Some(tx))
}

async fn read_updates(
    rpc: &mut Rpc,
    head: &Value,
    codebook: &[u16],
) -> Result<(Option<Source>, Option<Value>)> {
    let bloom = hex::decode(
        head["logsBloom"]
            .as_str()
            .context("missing bloom")?
            .strip_prefix("0x")
            .context("invalid bloom")?,
    )?;
    let hash = &head["hash"];
    let source = update(rpc, hash, &bloom, ORACLE, FEED).await?;
    let anchor = update(rpc, hash, &bloom, super::ORACLE, super::SPCX).await?;
    let input = |tx: Value| {
        tx["input"]
            .as_str()
            .map(str::to_owned)
            .context("missing input")
    };
    Ok((
        source
            .map(|tx| Source::decode(&input(tx)?, codebook))
            .transpose()?,
        anchor
            .map(|tx| super::pyth::decode(&input(tx)?))
            .transpose()?,
    ))
}

pub async fn run(
    mut heads: mpsc::Receiver<Value>,
    output: mpsc::Sender<Value>,
    url: String,
) -> Result<()> {
    let mut rpc = Rpc {
        url,
        ws: None,
        id: 0,
    };
    let codebook: Vec<u16> =
        serde_json::from_str(include_str!("../scripts/metric_spread_codebook.json"))?;
    ensure!(codebook.len() == 256, "incorrect spread codebook");
    let (mut source, mut anchor) = (None, None);
    let mut parent = Value::Null;
    while let Some(row) = heads.recv().await {
        let head = &row["payload"];
        if head["parentHash"] != parent {
            (source, anchor) = (None, None);
        }
        parent = head["hash"].clone();
        let result = read_updates(&mut rpc, head, &codebook).await;
        let mut record = json!({"kind":"block_quote","pool":POOL,"block":super::quantity(&head["number"]),
            "hash":head["hash"],"head_recv_ns":row["recv_ns"],"available_ns":super::now_ns(),
            "status":"warming_up"});
        match result {
            Ok((s, a)) => {
                if s.is_some() {
                    source = s;
                }
                if a.is_some() {
                    anchor = a;
                }
                if let (Some(s), Some(a), Some(t)) =
                    (source, &anchor, super::quantity(&head["timestamp"]))
                {
                    let anchor_time = a["publish_us"].as_u64().unwrap() / 1_000_000;
                    let source_time = s.time_ms / 1000;
                    if s.stalled
                        || s.price == 0
                        || t.checked_sub(source_time).is_none_or(|age| age > 15)
                        || t.checked_sub(anchor_time).is_none_or(|age| age > 15)
                    {
                        record["status"] = json!("stale_or_stalled");
                    } else {
                        let (bid, ask) = s.edges();
                        record["status"] = json!("source_quote");
                        record["source_bid_x64"] = json!(bid.to_string());
                        record["source_ask_x64"] = json!(ask.to_string());
                        record["source_publish_ms"] = json!(s.time_ms);
                        record["pyth_share_price_e8"] = a["price_e8"].clone();
                        record["pyth_publish_us"] = a["publish_us"].clone();
                    }
                }
            }
            Err(_) => {
                (source, anchor) = (None, None);
                record["status"] = json!("update_unavailable");
            }
        }
        if output.send(record).await.is_err() {
            break;
        }
    }
    Ok(())
}
