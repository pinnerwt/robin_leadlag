//! Public equity-token spot feeds; raced connections, dedup and warm rotation.
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
    task::JoinHandle,
    time::{Duration, timeout},
};
use tokio_tungstenite::{connect_async, tungstenite::Message};
fn utc() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}
fn emit(tx: &mpsc::Sender<Value>, row: Value) -> Result<()> {
    tx.try_send(row).context("receiver queue full or closed")
}
fn control(kind: &str, feed: &Value, id: u64, epoch: u64, start: Instant) -> Value {
    json!({"kind":kind,"venue":feed["venue"],"link":id,"epoch":epoch,"recv_ns":utc(),"mono_ns":start.elapsed().as_nanos() as u64})
}
fn quote(
    feed: &Value,
    symbol: &str,
    bid: Value,
    ask: Value,
    bq: Value,
    aq: Value,
    identity: String,
) -> Result<Value> {
    let asset = feed["instruments"][symbol]
        .as_object()
        .context("unknown instrument")?;
    ensure!(
        !bid.is_null() && !ask.is_null() && !bq.is_null() && !aq.is_null(),
        "missing BBO fields"
    );
    Ok(
        json!({"kind":"equity_bbo","venue":feed["venue"],"instrument":symbol,"ticker":asset["ticker"],"quote_currency":asset["quote_currency"],"instrument_type":asset.get("instrument_type").cloned().unwrap_or(json!("equity_token_spot")),"bid":bid,"ask":ask,"bid_qty":bq,"ask_qty":aq,"identity":identity}),
    )
}
fn decode(feed: &Value, row: &Value) -> Result<Vec<Value>> {
    let mut out = vec![];
    match feed["venue"].as_str().context("venue")? {
        "binance" => {
            let r = row.get("data").unwrap_or(row);
            if let Some(s) = r["s"].as_str() {
                let u = r["u"].as_u64().context("update_id")?;
                let mut q = quote(
                    feed,
                    s,
                    r["b"].clone(),
                    r["a"].clone(),
                    r["B"].clone(),
                    r["A"].clone(),
                    u.to_string(),
                )?;
                q["update_id"] = json!(u);
                q["exchange_timestamp"] = Value::Null;
                q["exchange_timestamp_unit"] = Value::Null;
                out.push(q);
            }
        }
        "kraken" => {
            if row["channel"] == "ticker" {
                for r in row["data"].as_array().context("ticker data")? {
                    let s = r["symbol"].as_str().context("symbol")?;
                    let stamp = r["timestamp"].as_str().context("ticker timestamp")?;
                    let key =
                        json!([stamp, r["bid"], r["ask"], r["bid_qty"], r["ask_qty"]]).to_string();
                    let mut q = quote(
                        feed,
                        s,
                        r["bid"].clone(),
                        r["ask"].clone(),
                        r["bid_qty"].clone(),
                        r["ask_qty"].clone(),
                        key,
                    )?;
                    q["exchange_timestamp"] = json!(stamp);
                    q["exchange_timestamp_unit"] = json!("rfc3339");
                    q["message_type"] = row["type"].clone();
                    out.push(q);
                }
            }
        }
        "bybit" => {
            if row["topic"]
                .as_str()
                .is_some_and(|s| s.starts_with("orderbook.1."))
            {
                let r = &row["data"];
                let s = r["s"].as_str().context("symbol")?;
                let u = r["u"].as_u64().context("update_id")?;
                let seq = r["seq"].as_u64().context("sequence")?;
                // Empty sides are withdrawals, not a stale previous price.
                let side = |k: &str| -> Result<(Value, Value)> {
                    let a = r[k].as_array().context("book side")?;
                    if a.is_empty() {
                        Ok((json!("0"), json!("0")))
                    } else {
                        ensure!(a[0].as_array().is_some_and(|v| v.len() == 2), "bad level");
                        Ok((a[0][0].clone(), a[0][1].clone()))
                    }
                };
                let (b, bq) = side("b")?;
                let (a, aq) = side("a")?;
                let mut q = quote(feed, s, b, a, bq, aq, format!("{seq}:{u}"))?;
                q["update_id"] = json!(u);
                q["sequence"] = json!(seq);
                q["exchange_timestamp"] = row["cts"].clone();
                q["exchange_timestamp_unit"] = json!("milliseconds");
                q["publish_timestamp_ms"] = row["ts"].clone();
                q["message_type"] = row["type"].clone();
                out.push(q);
            }
        }
        _ => anyhow::bail!("unsupported venue"),
    }
    Ok(out)
}
async fn socket(
    feed: &Value,
    id: u64,
    epoch: u64,
    start: Instant,
    tx: &mpsc::Sender<Value>,
) -> Result<()> {
    let venue = feed["venue"].as_str().context("venue")?;
    let (mut ws, _) = timeout(
        Duration::from_secs(15),
        connect_async(feed["url"].as_str().context("url")?),
    )
    .await??;
    emit(tx, control("connected", feed, id, epoch, start))?;
    let symbols: Vec<String> = feed["instruments"]
        .as_object()
        .context("instruments")?
        .keys()
        .cloned()
        .collect();
    let mut ack = HashSet::new();
    let mut ready = false;
    match venue {
 "binance"=>ws.send(Message::Text(json!({"method":"SUBSCRIBE","params":symbols.iter().map(|s|format!("{}@bookTicker",s.to_lowercase())).collect::<Vec<_>>(),"id":1}).to_string().into())).await?,
 "kraken"=>ws.send(Message::Text(json!({"method":"subscribe","params":{"channel":"ticker","symbol":symbols,"event_trigger":"bbo","snapshot":true}}).to_string().into())).await?,
 "bybit"=>{for s in &symbols{ws.send(Message::Text(json!({"op":"subscribe","req_id":s,"args":[format!("orderbook.1.{s}")]}).to_string().into())).await?;}},_=>unreachable!()}
    let mut heartbeat = tokio::time::interval(Duration::from_secs(20));
    heartbeat.tick().await;
    let mut last_recv = Instant::now();
    let connected = Instant::now();
    loop {
        tokio::select! {
         _=heartbeat.tick()=>{
          ensure!(last_recv.elapsed()<Duration::from_secs(60),"receive timeout");
          ensure!(ready || connected.elapsed()<Duration::from_secs(30),"subscription timeout");
          if venue=="bybit" {ws.send(Message::Text(json!({"op":"ping"}).to_string().into())).await?;}else{ws.send(Message::Ping(vec![].into())).await?;}
         },
         frame=ws.next()=>{
          let frame=frame.context("closed")??;let recv=utc();let mono=start.elapsed().as_nanos() as u64;last_recv=Instant::now();
          match frame {
           Message::Text(text)=>{
            let row:Value=serde_json::from_str(&text)?;
            if row["success"]==false || !row["error"].is_null() || row.get("code").is_some(){
             let mut event=control("subscription_error",feed,id,epoch,start);event["response"]=row;emit(tx,event)?;anyhow::bail!("subscription rejected");
            }
            let is_ack= match venue {
             "binance"=>{if row["id"]==1 && row.get("result").is_some() && row["result"].is_null(){ack.extend(symbols.iter().cloned());true}else{false}},
             "kraken"=>{if row["method"]=="subscribe" && row["success"]==true {if let Some(s)=row["result"]["symbol"].as_str(){ack.insert(s.to_owned());}true}else{false}},
             "bybit"=>{if row["op"]=="subscribe" && row["success"]==true{if let Some(s)=row["req_id"].as_str(){ack.insert(s.to_owned());}true}else{false}},_=>false};
            if is_ack {let mut event=control("subscribed",feed,id,epoch,start);event["response"]=row.clone();emit(tx,event)?;}
            if !ready && symbols.iter().all(|s|ack.contains(s)){ready=true;emit(tx,control("ready",feed,id,epoch,start))?;}
            for mut q in decode(feed,&row)?{q["recv_ns"]=json!(recv);q["mono_ns"]=json!(mono);q["link"]=json!(id);q["epoch"]=json!(epoch);emit(tx,q)?;}
           },Message::Ping(_)=>ws.flush().await?,Message::Close(_)=>anyhow::bail!("closed"),_=>{}
          }
         }
        }
    }
}
fn spawn(feed: Value, id: u64, start: Instant, tx: mpsc::Sender<Value>) -> JoinHandle<Result<()>> {
    tokio::spawn(async move {
        let mut epoch = 0;
        loop {
            let result = socket(&feed, id, epoch, start, &tx).await;
            let mut event = control("gap", &feed, id, epoch, start);
            event["reason"] = json!(if result.is_err() {
                "transport_or_decode_error"
            } else {
                "closed"
            });
            emit(&tx, event)?;
            epoch += 1;
            tokio::time::sleep(Duration::from_secs((1u64 << epoch.min(5)).min(30))).await;
        }
    })
}
#[derive(Default)]
struct Stats {
    samples: Vec<u64>,
    wins: u64,
    duplicates: u64,
}
impl Stats {
    fn add(&mut self, lag: u64) {
        if self.samples.len() < 20000 {
            self.samples.push(lag)
        }
    }
    fn p90(&self) -> u64 {
        let mut v = self.samples.clone();
        v.sort_unstable();
        v.get(v.len() * 9 / 10).copied().unwrap_or(0)
    }
}
struct Link {
    feed: usize,
    ready: bool,
    task: JoinHandle<Result<()>>,
    stats: Stats,
}
struct Dedup {
    seen: HashMap<String, (u64, u64, bool)>,
    order: VecDeque<String>,
    limit: usize,
}
impl Dedup {
    fn observe(&mut self, key: String, mono: u64, link: u64) -> Option<(u64, u64, bool)> {
        if let Some(v) = self.seen.get_mut(&key) {
            let fresh_match = v.1 != link && !v.2;
            if fresh_match {
                v.2 = true;
            }
            return Some((v.0, v.1, fresh_match));
        }
        self.seen.insert(key.clone(), (mono, link, false));
        self.order.push_back(key);
        while self.order.len() > self.limit {
            if let Some(k) = self.order.pop_front() {
                self.seen.remove(&k);
            }
        }
        None
    }
}
#[tokio::main(worker_threads = 2)]
async fn main() -> Result<()> {
    let path = std::env::args()
        .nth(1)
        .context("usage: equity_capture config.json [seconds]")?;
    let config: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let feeds = config["feeds"].as_array().context("feeds")?.clone();
    ensure!(!feeds.is_empty(), "empty feeds");
    let connections = config["connections_per_venue"]
        .as_u64()
        .context("connections_per_venue")?;
    ensure!((2..=8).contains(&connections), "connection count");
    let rotation = config["rotation_seconds"]
        .as_u64()
        .context("rotation_seconds")?;
    ensure!(rotation > 0, "rotation_seconds");
    let min_samples = config["rotation_min_samples"]
        .as_u64()
        .context("rotation_min_samples")? as usize;
    let warmup = config["rotation_warmup_seconds"]
        .as_u64()
        .context("rotation_warmup_seconds")?;
    let duration = std::env::args()
        .nth(2)
        .map(|s| s.parse())
        .transpose()?
        .unwrap_or(
            config["duration_seconds"]
                .as_u64()
                .context("duration_seconds")?,
        );
    for f in &feeds {
        ensure!(
            matches!(f["venue"].as_str(), Some("binance" | "kraken" | "bybit")),
            "only supported spot feeds"
        );
        ensure!(
            f["instruments"].as_object().is_some_and(|m| !m.is_empty()),
            "empty instruments"
        );
    }
    let start = Instant::now();
    let (tx, mut rx) = mpsc::channel(65536);
    let mut links = HashMap::<u64, Link>::new();
    let mut next_id = 0;
    for (fi, f) in feeds.iter().enumerate() {
        for _ in 0..connections {
            links.insert(
                next_id,
                Link {
                    feed: fi,
                    ready: false,
                    task: spawn(f.clone(), next_id, start, tx.clone()),
                    stats: Stats::default(),
                },
            );
            next_id += 1;
        }
    }
    let (disk_tx, disk_rx) = std::sync::mpsc::sync_channel::<Vec<u8>>(65536);
    let writer = std::thread::spawn(move || -> Result<()> {
        let mut output = BufWriter::with_capacity(262144, io::stdout().lock());
        output.write_all(journal::MAGIC)?;
        while let Ok(v) = disk_rx.recv() {
            output.write_all(&v)?;
        }
        output.flush()?;
        Ok(())
    });
    let write = |r: &Value| -> Result<()> {
        disk_tx
            .try_send(journal::frame(r)?)
            .context("disk queue unavailable")
    };
    write(
        &json!({"kind":"equity_session","recv_ns":utc(),"config":config,"timestamp_semantics":"Ohio application receipt before JSON decode; no synthetic network offsets","kraken_dedup":"source_timestamp_and_full_bbo","no_perpetuals":true}),
    )?;
    let mut dedup = Dedup {
        seen: HashMap::new(),
        order: VecDeque::new(),
        limit: config["dedup_cache_entries"]
            .as_u64()
            .context("dedup_cache_entries")? as usize,
    };
    ensure!(dedup.limit > 0, "dedup cache size");
    let mut pending = HashMap::<u64, (u64, Instant)>::new();
    let mut seen_counts = HashMap::<String, u64>::new();
    let mut last_recv = HashMap::<String, u64>::new();
    let mut highwater = HashMap::<String, u64>::new();
    let mut unique = 0u64;
    let mut duplicates = 0u64;
    let mut last_rotation = start;
    let mut failure = None;
    let stop = tokio::time::sleep(Duration::from_secs(duration));
    tokio::pin!(stop);
    let mut stats_tick = tokio::time::interval(Duration::from_secs(5));
    let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    loop {
        tokio::select! {
         _=&mut stop=>break,
         _=tokio::signal::ctrl_c()=>break,
         _=term.recv()=>break,
         _=stats_tick.tick()=>{
          if links.values().any(|l|l.task.is_finished()){failure=Some("receiver_task_terminated");break;}
          let expired:Vec<_>=pending.iter().filter(|(_,(_,t))|t.elapsed()>Duration::from_secs(warmup)).map(|(id,_)|*id).collect();
          for id in expired{let (old,_)=pending.remove(&id).unwrap();if let Some(l)=links.remove(&id){l.task.abort();}write(&json!({"kind":"rotation_cancelled","link":id,"old_link":old,"recv_ns":utc(),"reason":"replacement_not_ready"}))?;}
          if last_rotation.elapsed()>=Duration::from_secs(rotation){
           for fi in 0..feeds.len(){
            if pending.keys().any(|id|links.get(id).is_some_and(|l|l.feed==fi)){continue;}
            let candidate=links.iter().filter(|(_,l)|l.feed==fi&&l.ready&&l.stats.samples.len()>=min_samples).max_by_key(|(_,l)|l.stats.p90()).map(|(id,l)|(*id,l.stats.p90()));
            if let Some((old,p90))=candidate{
             let id=next_id;next_id+=1;links.insert(id,Link{feed:fi,ready:false,task:spawn(feeds[fi].clone(),id,start,tx.clone()),stats:Stats::default()});pending.insert(id,(old,Instant::now()));
             write(&json!({"kind":"rotation_start","venue":feeds[fi]["venue"],"old_link":old,"new_link":id,"p90_relative_lag_ns":p90,"recv_ns":utc()}))?;
            }else{write(&json!({"kind":"rotation_skipped","venue":feeds[fi]["venue"],"reason":"insufficient_matched_samples","recv_ns":utc()}))?;}
           }
           for l in links.values_mut(){l.stats=Stats::default();}last_rotation=Instant::now();
          }
          let link_stats:Vec<_>=links.iter().map(|(id,l)|json!({"link":id,"venue":feeds[l.feed]["venue"],"ready":l.ready,"matched_samples":l.stats.samples.len(),"p90_relative_lag_ns":l.stats.p90(),"wins":l.stats.wins,"duplicates":l.stats.duplicates})).collect();
          let row=json!({"kind":"equity_coverage","recv_ns":utc(),"unique":unique,"duplicates":duplicates,"counts":seen_counts,"last_quote_recv_ns":last_recv,"links":link_stats,"pending_rotations":pending.len()});eprintln!("{row}");if write(&row).is_err(){failure=Some("disk_queue_unavailable");break;}
         },
         row=rx.recv()=>{
          let Some(mut row)=row else{failure=Some("receiver_queue_closed");break};let id=row["link"].as_u64().context("link")?;
          if !links.contains_key(&id) && row["kind"]!="equity_bbo"{continue;}
          if row["kind"]=="ready"{
           links.get_mut(&id).unwrap().ready=true;
           if let Some((old,_))=pending.remove(&id){if let Some(l)=links.remove(&old){l.task.abort();}write(&json!({"kind":"rotation_complete","old_link":old,"new_link":id,"recv_ns":utc()}))?;}
          }else if row["kind"]=="gap"{links.get_mut(&id).unwrap().ready=false;}
          if row["kind"]=="equity_bbo"{
           let key=format!("{}|{}|{}",row["venue"],row["instrument"],row["identity"]);let mono=row["mono_ns"].as_u64().unwrap();
           if let Some((first,first_link,fresh_match))=dedup.observe(key,mono,id){duplicates+=1;if let Some(l)=links.get_mut(&id){l.stats.duplicates+=1;if first_link!=id{l.stats.add(mono.saturating_sub(first));}}if fresh_match{if let Some(winner)=links.get_mut(&first_link){winner.stats.add(0);}}continue;}
           if let Some(l)=links.get_mut(&id){l.stats.wins+=1;}unique+=1;
           *seen_counts.entry(format!("{}:{}",row["venue"].as_str().unwrap(),row["instrument"].as_str().unwrap())).or_default()+=1;
           let instrument_key=format!("{}:{}",row["venue"].as_str().unwrap(),row["instrument"].as_str().unwrap());
                    last_recv.insert(instrument_key.clone(),row["recv_ns"].as_u64().unwrap());
                    if let Some(seq)=row["sequence"].as_u64().or_else(||row["update_id"].as_u64()) {
                        let previous=highwater.entry(instrument_key).or_insert(seq);
                        row["is_late"]=json!(seq<*previous);
                        *previous=(*previous).max(seq);
                    } else {row["is_late"]=Value::Null;}
                    row.as_object_mut().unwrap().remove("identity");
          }
          if write(&row).is_err(){failure=Some("disk_queue_unavailable");break;}
         }
        }
    }
    for (_, l) in links {
        l.task.abort();
    }
    // Record an explicit boundary; do not claim a final drained, uninterrupted state.
    disk_tx.send(journal::frame(&json!({"kind":"equity_capture_end","recv_ns":utc(),"unique":unique,"duplicates":duplicates,"failure":failure,"boundary":"stop_receive_and_close"}))?).context("writer closed")?;
    drop(disk_tx);
    writer
        .join()
        .map_err(|_| anyhow::anyhow!("writer panic"))??;
    ensure!(failure.is_none(), "capture failed: {failure:?}");
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    fn feed(venue: &str, symbol: &str) -> Value {
        json!({"venue":venue,"instruments":{symbol:{"ticker":"NVDA","quote_currency":"USD"}}})
    }
    #[test]
    fn seq_dedup_and_expiry() {
        let mut d = Dedup {
            seen: HashMap::new(),
            order: VecDeque::new(),
            limit: 2,
        };
        assert_eq!(d.observe("a".into(), 10, 0), None);
        assert_eq!(d.observe("a".into(), 20, 1), Some((10, 0, true)));
        d.observe("b".into(), 30, 0);
        d.observe("c".into(), 40, 0);
        assert_eq!(d.observe("a".into(), 50, 1), None);
    }
    #[test]
    fn binance_exact_decimals() {
        let r = decode(
            &feed("binance", "NVDABUSDT"),
            &json!({"s":"NVDABUSDT","u":123,"b":"100.00100000","a":"100.00200000","B":"2","A":"3"}),
        )
        .unwrap();
        assert_eq!(r[0]["bid"], "100.00100000");
        assert_eq!(r[0]["identity"], "123");
        assert!(r[0]["exchange_timestamp"].is_null());
    }
    #[test]
    fn bybit_resend_dedup_and_withdrawal() {
        let f = feed("bybit", "NVDAXUSDT");
        let mut r = json!({"topic":"orderbook.1.NVDAXUSDT","ts":1000,"cts":990,"type":"snapshot","data":{"s":"NVDAXUSDT","u":5,"seq":8,"b":[],"a":[["101","2"]]}});
        let a = decode(&f, &r).unwrap();
        r["ts"] = json!(2000);
        let b = decode(&f, &r).unwrap();
        assert_eq!(a[0]["identity"], b[0]["identity"]);
        assert_eq!(a[0]["bid"], "0");
    }
    #[test]
    fn kraken_full_bbo_identity() {
        let f = feed("kraken", "NVDAx/USD");
        let mut r = json!({"channel":"ticker","type":"update","data":[{"symbol":"NVDAx/USD","timestamp":"2026-11-19T12:00:00.123456Z","bid":100,"ask":101,"bid_qty":2,"ask_qty":3}]});
        let a = decode(&f, &r).unwrap();
        r["data"][0]["bid_qty"] = json!(4);
        let b = decode(&f, &r).unwrap();
        assert_ne!(a[0]["identity"], b[0]["identity"]);
    }
}
