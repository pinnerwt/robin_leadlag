//! Standalone execution owner. Local binary IPC is a trusted quote/account-observer boundary.
//! Market-data freshness is independently checked. ACKs never settle orders.
pub mod config;
mod feeds;
use anyhow::{Context, Result, ensure};
use config::{BASE, Config, Mode, POOL, QUOTE, address};
use robin_leadlag::execution::{
    self, Amount, Observation, Side, baseline,
    portfolio::{AccountSnapshot, Portfolio},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    io::Write,
    os::unix::fs::PermissionsExt,
    path::Path,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{
    io::{AsyncReadExt,AsyncWriteExt},
    net::UnixListener,
    sync::{mpsc, watch},
};
#[path = "../journal.rs"]
mod wire;
pub fn now_ns() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos() as u64
}
fn hexnum(v: &Value) -> Result<u64> {
    Ok(u64::from_str_radix(
        v.as_str().context("hex number")?.trim_start_matches("0x"),
        16,
    )?)
}
fn hash(s: &str) -> Result<[u8; 32]> {
    hex::decode(s.trim_start_matches("0x"))?
        .try_into()
        .map_err(|_| anyhow::anyhow!("hash length"))
}
fn fresh(now: u64, stamp: u64, ms: u64) -> bool {
    now.checked_sub(stamp).is_some_and(|d| d <= ms * 1_000_000)
}
#[derive(Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Input {
    Synchronize {
        epoch: u64,
        anchor_number: u64,
        anchor_hash: String,
        executor_codehash: String,
        account: AccountSnapshot,
    },
    Quote {
        observation: Observation,
    },
    Receipt {
        receipt: Value,
    },
    Gap {
        reason: String,
    },
    FeedSeen { tx: String, received_ns:u64, block_hash:String, sequence:u64 },
}
enum Event {
    Bbo {
        link: usize,
        recv: u64,
        id: u64,
        bid: String,
        ask: String,
    },
    BinanceLink(usize, bool),
    Head {
        recv: u64,
        head: Value,
    },
    ChainGap,
    Submission(Value),
    Input(Input),
    Producer(bool),
    Tick,
    Stop,
}
struct Bbo {
    recv: u64,
    bid: Amount,
    ask: Amount,
}
struct Audit {
    file: File,
}
impl Audit {
    fn open(path: &str) -> Result<Self> {
        let path = Path::new(path);
        std::fs::create_dir_all(path.parent().context("audit parent")?)?;
        let mut file = OpenOptions::new().append(true).create(true).open(path)?;
        if file.metadata()?.len() == 0 {
            file.write_all(wire::MAGIC)?;
        }
        Ok(Self { file })
    }
    fn write(&mut self, row: Value) -> Result<()> {
        self.file.write_all(&wire::frame(&row)?)?;
        Ok(())
    }
}
struct Engine {
    c: Config,
    credentials: Option<config::Credentials>,
    credential_error: Option<String>,
    wallet: Option<Portfolio>,
    bbo: Option<Bbo>,
    links: Vec<bool>,
    sequence: u64,
    first: BTreeMap<u64, u64>,
    races: Vec<(u64, u128)>,
    hashes: BTreeMap<u64, [u8; 32]>,
    head: Option<(u64, [u8; 32], u64)>,
    chain_epoch: u64,
    account_epoch: Option<u64>,
    quote: Option<Observation>,
    producer: bool,
    counts: BTreeMap<String, u64>,
    last_error: Option<String>,
    audit: Audit,
    rotations: Vec<watch::Sender<u64>>,
    last_rotation: u64,
    submit: tokio::runtime::Handle,
    submit_client: reqwest::Client,
    event_tx: Option<mpsc::Sender<Event>>,
    state_tx: Option<watch::Sender<Value>>,
    circuit: execution::circuit::Circuit,
    last_settled_block: u64,
}
impl Engine {
    fn new(
        c: Config,
        rotations: Vec<watch::Sender<u64>>,
        submit: tokio::runtime::Handle,
    ) -> Result<Self> {
        let (credentials, credential_error) = match c.credentials() {
            Ok(x) => (Some(x), None),
            Err(e) => (None, Some(e.to_string())),
        };
        let n = c.binance_connections;
        let audit = Audit::open(&c.audit_file)?;
        let submit_client = execution::transport::client(Duration::from_secs(3))?;
        let circuit=execution::circuit::Circuit::open(Path::new(&c.state_directory),c.circuit.clone())?;
        Ok(Self {
            c,
            credentials,
            credential_error,
            wallet: None,
            bbo: None,
            links: vec![false; n],
            sequence: 0,
            first: BTreeMap::new(),
            races: vec![(0, 0); n],
            hashes: BTreeMap::new(),
            head: None,
            chain_epoch: 0,
            account_epoch: None,
            quote: None,
            producer: false,
            counts: BTreeMap::new(),
            last_error: None,
            audit,
            rotations,
            last_rotation: now_ns(),
            submit,
            submit_client,
            event_tx: None,
            state_tx: None,
            circuit,
            last_settled_block: 0,
        })
    }
    fn count(&mut self, name: &str) {
        *self.counts.entry(name.into()).or_default() += 1;
    }
    fn invalidate(&mut self) {
        self.quote = None;
        self.account_epoch = None;
        if let Some(p) = &mut self.wallet {
            p.disconnect();
        }
    }
    fn head_fresh(&self, now: u64) -> bool {
        self.head
            .is_some_and(|h| fresh(now, h.2, self.c.max_head_age_ms))
    }
    fn input(&mut self, input: Input) -> Result<()> {
        let now = now_ns();
        match input {
            Input::FeedSeen {tx,received_ns,block_hash,sequence}=>{self.audit.write(json!({"kind":"own_nitro_seen","tx":tx,"recv_ns":received_ns,"block_hash":block_hash,"sequence":sequence}))?;self.count("own_nitro_seen");}
            Input::Gap { reason: _ } => {
                self.invalidate();
                self.count("producer_gap");
            }
            Input::Synchronize {
                epoch,
                anchor_number,
                anchor_hash,
                executor_codehash,
                account,
            } => {
                ensure!(self.head_fresh(now), "canonical heads unavailable/stale");
                ensure!(
                    self.hashes.get(&anchor_number) == Some(&hash(&anchor_hash)?),
                    "account anchor not on observed chain"
                );
                ensure!(
                    fresh(now, account.observed_ns, self.c.max_account_age_ms),
                    "stale account snapshot"
                );
                ensure!(
                    self.c
                        .executor_codehash
                        .as_ref()
                        .is_some_and(|h| h.eq_ignore_ascii_case(&executor_codehash)),
                    "executor codehash mismatch"
                );
                let credentials = self
                    .credentials
                    .as_ref()
                    .context("credentials unavailable")?;
                let settings = self.c.settings(credentials)?;
                let permission = account
                    .permissions
                    .get("ETH")
                    .context("ETH permissions missing")?;
                ensure!(
                    permission.executor_verified && permission.provider_access_verified,
                    "executor/provider verification missing"
                );
                if self.wallet.is_none() {
                    if !Path::new(&self.c.state_directory)
                        .join("metric-execution.slots")
                        .exists()
                    {
                        ensure!(
                            account.positions.get("ETH")
                                == Some(&credentials.baseline.initial_base),
                            "funded WETH differs from declared baseline"
                        );
                        ensure!(
                            account.cash.0
                                >= baseline::parse_quantity(&self.c.initial_cash_usdg, 6)?.0,
                            "less than 100 USDG available"
                        );
                    }
                    self.wallet = Some(Portfolio::open(
                        Path::new(&self.c.state_directory),
                        settings,
                        account.nonce,
                        account.cash,
                    )?);
                }
                self.wallet.as_mut().unwrap().synchronize(epoch, account)?;
                self.account_epoch = Some(epoch);
                self.quote = None;
                self.count("account_sync");
            }
            Input::Quote { observation } => {
                ensure!(
                    self.account_epoch == Some(observation.epoch),
                    "quote epoch not synchronized"
                );
                ensure!(observation.pool == address(POOL)?, "wrong pool");
                ensure!(
                    self.quote
                        .as_ref()
                        .is_none_or(|q| observation.state_version >= q.state_version),
                    "quote state version regressed"
                );
                ensure!(
                    fresh(now, observation.state_received_ns, self.c.max_state_age_ms),
                    "stale/future quote"
                );
                self.quote = Some(observation);
                self.count("quotes");
            }
            Input::Receipt { receipt: r } => {
                let incoming=r["transactionHash"].as_str().context("receipt hash")?;
                if self.wallet.as_ref().and_then(|p|p.pending()).is_none_or(|p|format!("0x{}",hex::encode(p.order.hash))!=incoming) {
                    self.count("stale_receipt_ignored");return Ok(());
                }
                ensure!(self.head_fresh(now), "receipt observer is stale");
                let n = hexnum(&r["blockNumber"])?;
                let canonical = *self
                    .hashes
                    .get(&n)
                    .context("receipt block not in canonical window")?;
                let p = self.wallet.as_mut().context("wallet not initialized")?;
                let pending = p.pending().context("no pending order")?.clone();
                let evidence = execution::receipt::decode(
                    &r,
                    &pending,
                    p.settings().wallet,
                    address(self.c.executor.as_deref().context("executor")?)?,
                    address(BASE)?,
                    address(QUOTE)?,
                    &p.inventory("ETH")?,
                    canonical,
                    self.head.unwrap().0,
                )?;
                self.circuit.receipt(incoming.to_owned(),evidence.success,now)?;
                let resumed=p.settle_and_resume(&evidence,u128::from(self.c.gas_limit)*self.c.max_fee_per_gas.parse::<u128>()?)?;
                self.last_settled_block=n;
                if !resumed {self.account_epoch=None;}
                self.count(if resumed {"local_account_resume"}else{"account_refresh_required"});
                self.quote = None;
                self.count(if evidence.success { "fills" } else { "reverts" });
                self.audit.write(json!({"kind":"receipt_settled","recv_ns":now,"tx":r["transactionHash"],"success":evidence.success,"usdg_amount":evidence.usdg_amount,"evidence_source":r["_source"],"evidence_received_ns":r["_observed_ns"]}))?;
            }
        }
        Ok(())
    }
    fn decide(&mut self) -> Result<()> {
        let now = now_ns();
        if self.circuit.halt().is_some() || !self.producer || !self.head_fresh(now) {
            return Ok(());
        }
        let (Some(b), Some(mut o), Some(p)) = (&self.bbo, self.quote.clone(), &mut self.wallet)
        else {
            return Ok(());
        };
        if !fresh(now, b.recv, self.c.max_bbo_age_ms)
            || !fresh(now, o.state_received_ns, self.c.max_state_age_ms)
        {
            return Ok(());
        }
        o.bid_e8 = b.bid;
        o.ask_e8 = b.ask;
        o.bbo_received_ns = b.recv;
        o.provider_valid_until_ns = o
            .provider_valid_until_ns
            .min(now + self.c.order_ttl_ms * 1_000_000);
        let baseline = p.settings().stocks["ETH"].baseline.initial_base.0;
        let inventory = p.inventory("ETH")?;
        // Pilot is buy-first only. Relative-long closes back to the fixed baseline.
        if inventory.base.0 < baseline {
            return Ok(());
        }
        let side = if inventory.base.0 > baseline {
            Side::Sell
        } else {
            Side::Buy
        };
        let Some(intent) = p.signal("ETH", side, &o, now)? else {
            return Ok(());
        };
        if self.c.mode == Mode::Standby {
            self.count("standby_signals");
            return Ok(());
        }
        if !self.circuit.before_order(now)? {return Ok(())}
        let pending = p.reserve(
            "ETH",
            side,
            &o,
            now,
            self.credentials
                .as_ref()
                .and_then(|c| c.key.as_ref())
                .context("key not configured")?,
            self.c.gas_limit,
            self.c.max_fee_per_gas.parse()?,
            self.c.priority_fee_per_gas.parse()?,
        )?;
        // The durable reservation already succeeded. Submit immediately, without a
        // modeled 20ms sleep or awaiting account/gas/quote RPC.
        for (endpoint,url) in self.c.submit_urls.iter().cloned().enumerate() {
            let order=pending.order.clone();let client=self.submit_client.clone();let events=self.event_tx.clone();
            self.submit.spawn(async move {
                let ack=execution::transport::submit(&client,&url,endpoint,&order).await;
                let report=json!({"tx":format!("0x{}",hex::encode(order.hash)),"acks":[ack]});
                if let Some(events)=events {let _=events.send(Event::Submission(report)).await;}
            });
        }
        self.count("submitted");
        self.audit.write(json!({"kind":"submitted","recv_ns":now,"tx":format!("0x{}",hex::encode(pending.order.hash)),"nonce":pending.order.nonce,"intent":intent}))?;
        Ok(())
    }
    fn handle(&mut self, event: Event) -> Result<bool> {
        match event {
            Event::Submission(report)=>{
                let accepted=report["acks"].as_array().is_some_and(|a|a.iter().any(|a|a["matched_hash"]==true));
                self.count(if accepted {"submission_acknowledged"} else {"submission_unconfirmed"});
                self.audit.write(json!({"kind":"submission_result","recv_ns":now_ns(),"result":report}))?;
            }
            Event::Stop => {
                self.invalidate();
                self.status(true)?;
                return Ok(false);
            }
            Event::Producer(up) => {
                self.producer = up;
                self.invalidate();
                self.count(if up {
                    "producer_connected"
                } else {
                    "producer_disconnected"
                });
            }
            Event::Input(input) => {
                if let Err(e) = self.input(input) {
                    self.count("input_rejected");
                    self.last_error = Some(e.to_string());
                    self.invalidate();
                }
            }
            Event::ChainGap => {
                self.head = None;
                self.hashes.clear();
                self.chain_epoch += 1;
                self.invalidate();
                self.count("chain_gap");
            }
            Event::Head { recv, head } => {
                let n = hexnum(&head["number"])?;
                let h = hash(head["hash"].as_str().context("head hash")?)?;
                if self.hashes.get(&n) == Some(&h) {
                    return Ok(true);
                }
                if let Some((old, prev, _)) = self.head {
                    if n != old + 1
                        || hash(head["parentHash"].as_str().context("parent hash")?)? != prev
                    {
                        self.invalidate();
                        self.hashes.clear();
                        self.chain_epoch += 1;
                        self.count("chain_discontinuity");
                    }
                }
                self.hashes.insert(n, h);
                while self.hashes.len() > 4096 {
                    self.hashes.pop_first();
                }
                self.head = Some((n, h, recv));
                self.count("heads");
            }
            Event::BinanceLink(link, up) => {
                self.links[link] = up;
                if !self.links.iter().any(|x| *x) {
                    self.bbo = None;
                }
                self.count(if up {
                    "binance_connected"
                } else {
                    "binance_disconnected"
                });
            }
            Event::Bbo {
                link,
                recv,
                id,
                bid,
                ask,
            } => {
                let first = *self.first.entry(id).or_insert(recv);
                let delay = recv.saturating_sub(first);
                self.races[link].0 += 1;
                self.races[link].1 += u128::from(delay);
                while self.first.len() > 8192 {
                    self.first.pop_first();
                }
                if id <= self.sequence {
                    self.count("bbo_duplicate_or_late");
                    return Ok(true);
                }
                self.sequence = id;
                let bid = baseline::parse_quantity(&bid, 8)?;
                let ask = baseline::parse_quantity(&ask, 8)?;
                if bid.0 == 0 || ask.0 < bid.0 {
                    self.bbo = None;
                    self.count("invalid_bbo");
                } else {
                    self.bbo = Some(Bbo { recv, bid, ask });
                    self.count("bbo");
                }
            }
            Event::Tick => {
                let next=match self.c.reload_mode(){Ok(mode)=>mode,Err(e)=>{self.last_error=Some(e.to_string());self.invalidate();Mode::Standby}};
                if self.c.mode!=next {
                    self.c.mode=next;
                    self.audit.write(json!({"kind":"mode_changed","recv_ns":now_ns(),"mode":next}))?;
                    self.count("mode_changes");
                }
                let now = now_ns();
                if now - self.last_rotation >= self.c.rotate_seconds * 1_000_000_000 {
                    if self.links.iter().filter(|x| **x).count() > 1 {
                        if let Some((link, _)) = self
                            .races
                            .iter()
                            .enumerate()
                            .filter(|(i, x)| self.links[*i] && x.0 >= 100)
                            .max_by_key(|(_, x)| x.1 / u128::from(x.0))
                        {
                            let _ = self.rotations[link].send(now);
                            self.count("binance_slowest_rotations");
                        }
                    }
                    self.last_rotation = now;
                    self.races.fill((0, 0));
                }
                self.status(false)?;
            }
        }
        if let Err(e) = self.decide() {
            self.last_error = Some(e.to_string());
            self.count("admission_error");
            self.invalidate();
        }
        self.publish_state();
        Ok(true)
    }
    fn view(&self)->Value {
        json!({"kind":"trader_state","last_settled_block":self.last_settled_block,"head":self.head.map(|h|h.0),"head_hash":self.head.map(|h|format!("0x{}",hex::encode(h.1))),"chain_epoch":self.chain_epoch,"account_epoch":self.account_epoch,"baseline_raw":self.credentials.as_ref().map(|c|c.baseline.initial_base),"inventory":self.wallet.as_ref().and_then(|p|p.inventory("ETH").ok()),"pending_hash":self.wallet.as_ref().and_then(|p|p.pending()).map(|p|format!("0x{}",hex::encode(p.order.hash))),"circuit_halt":self.circuit.halt()})
    }
    fn publish_state(&self) {
        if let Some(tx)=&self.state_tx {let value=self.view();tx.send_if_modified(|old|{if *old==value{return false}*old=value;true});}
    }
    fn status(&self, stopped: bool) -> Result<()> {
        let now = now_ns();
        let mut blockers = vec![];
        if self.circuit.halt().is_some(){blockers.push("circuit_breaker");}
        if self.c.mode != Mode::Live {
            blockers.push("standby_mode");
        }
        if self
            .credentials
            .as_ref()
            .and_then(|c| c.key.as_ref())
            .is_none()
        {
            blockers.push("private_key_missing");
        }
        if self.c.executor.is_none() {
            blockers.push("executor_not_configured");
        }
        if !self.producer {
            blockers.push("state_account_observer_not_connected");
        }
        if self.account_epoch.is_none() {
            blockers.push("account_not_synchronized");
        }
        if !self.head_fresh(now) {
            blockers.push("canonical_head_not_fresh");
        }
        if self
            .bbo
            .as_ref()
            .is_none_or(|b| !fresh(now, b.recv, self.c.max_bbo_age_ms))
        {
            blockers.push("bbo_not_fresh");
        }
        if self
            .quote
            .as_ref()
            .is_none_or(|q| !fresh(now, q.state_received_ns, self.c.max_state_age_ms))
        {
            blockers.push("pool_quote_not_fresh");
        }
        if self.wallet.as_ref().is_some_and(|p| p.pending().is_some()) {
            blockers.push("pending_receipt");
        }
        let v = json!({"pid":std::process::id(),"updated_ns":now,"stopped":stopped,"mode":self.c.mode,"pool":POOL,"additional_long_usdg":self.c.additional_long_usdg,"baseline_raw":self.credentials.as_ref().map(|c|c.baseline.initial_base),"declared_hedge_raw":self.credentials.as_ref().map(|c|c.baseline.declared_exchange_short),"open_bps":self.c.open_bps,"close_bps":self.c.close_bps,"entry_side":"buy","execution_budget_ms":self.c.execution_budget_ms,"artificial_execution_sleep":false,"blockers":blockers,"credentials_error":self.credential_error,"last_error":self.last_error,"binance_links":self.links,"binance_sequence":self.sequence,"bbo_received_ns":self.bbo.as_ref().map(|b|b.recv),"head":self.head.map(|h|h.0),"head_received_ns":self.head.map(|h|h.2),"chain_epoch":self.chain_epoch,"counts":self.counts,"inventory":self.wallet.as_ref().and_then(|p|p.inventory("ETH").ok()),"pending_hash":self.wallet.as_ref().and_then(|p|p.pending()).map(|p|format!("0x{}",hex::encode(p.order.hash))),"zero_pretrade_rpc":true,"circuit_halt":self.circuit.halt()});
        let path = Path::new(&self.c.status_file);
        std::fs::create_dir_all(path.parent().context("status parent")?)?;
        let tmp = path.with_extension("tmp");
        std::fs::write(&tmp, serde_json::to_vec_pretty(&v)?)?;
        std::fs::rename(tmp, path)?;
        Ok(())
    }
}
pub async fn run(c: Config) -> Result<()> {
    std::fs::create_dir_all(&c.state_directory)?;
    let lock = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(Path::new(&c.state_directory).join("runtime.lock"))?;
    lock.try_lock().context("trading runtime already running")?;
    let path = Path::new(&c.input_socket);
    std::fs::create_dir_all(path.parent().context("socket directory")?)?;
    if path.exists() {
        ensure!(
            std::os::unix::net::UnixStream::connect(path).is_err(),
            "input socket is already owned"
        );
        std::fs::remove_file(path)?;
    }
    let listener = UnixListener::bind(path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    let (tx, mut rx) = mpsc::channel(4096);
    let mut rotation = vec![];
    let mut tasks = vec![];
    for link in 0..c.binance_connections {
        let (sender, receiver) = watch::channel(0);
        rotation.push(sender);
        tasks.push(tokio::spawn(feeds::binance(
            c.binance_ws_url.clone(),
            link,
            tx.clone(),
            receiver,
        )));
    }
    tasks.push(tokio::spawn(feeds::heads(
        c.chain_ws_url.clone(),
        tx.clone(),
    )));
    let (state_tx,state_rx)=watch::channel(Value::Null);
    let input_tx = tx.clone();
    tasks.push(tokio::spawn(async move {
        loop {
            let Ok((mut peer, _)) = listener.accept().await else {
                return;
            };
            let (mut peer,mut output)=peer.into_split();
            let mut states=state_rx.clone();
            let outbound=tokio::spawn(async move {
                output.write_all(wire::MAGIC).await?;
                loop {
                    let mut state=states.borrow_and_update().clone();state["updated_ns"]=json!(now_ns());
                    output.write_all(&wire::frame(&state)?).await?;
                    if states.changed().await.is_err(){break}
                }
                Ok::<_,anyhow::Error>(())
            });
            let _ = input_tx.send(Event::Producer(true)).await;
            let result = async {
                let mut magic = [0; 8];
                peer.read_exact(&mut magic).await?;
                ensure!(&magic == wire::MAGIC, "input magic");
                loop {
                    let mut length = [0; 4];
                    peer.read_exact(&mut length).await?;
                    let n = u32::from_le_bytes(length) as usize;
                    ensure!(n > 0 && n <= 1024 * 1024, "input frame exceeds 1MiB");
                    let mut b = vec![0; n];
                    peer.read_exact(&mut b).await?;
                    let input: Input = serde_json::from_value(wire::parse(&b)?)?;
                    input_tx
                        .send(Event::Input(input))
                        .await
                        .context("engine stopped")?;
                }
                #[allow(unreachable_code)]
                Ok::<_, anyhow::Error>(())
            }
            .await;
            let _ = result;
            outbound.abort();
            if input_tx.send(Event::Producer(false)).await.is_err() {
                return;
            }
        }
    }));
    let tick = tx.clone();
    tasks.push(tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(1));
        loop {
            interval.tick().await;
            if tick.send(Event::Tick).await.is_err() {
                break;
            }
        }
    }));
    let runtime = tokio::runtime::Handle::current();
    let socket = c.input_socket.clone();
    let mut engine = Engine::new(c, rotation, runtime)?;
    engine.state_tx=Some(state_tx);
    engine.publish_state();
    engine.event_tx=Some(tx.clone());
    let warm_client=engine.submit_client.clone();let warm_urls=engine.c.submit_urls.clone();
    tasks.push(tokio::spawn(async move {loop {for url in &warm_urls {
        if let Ok(response)=warm_client.post(url).json(&json!({"jsonrpc":"2.0","id":0,"method":"web3_clientVersion","params":[]})).send().await {let _=response.bytes().await;}
    }tokio::time::sleep(Duration::from_secs(30)).await;}}));
    engine.status(false)?;
    let worker = tokio::task::spawn_blocking(move || -> Result<()> {
        let _lock = lock;
        while let Some(e) = rx.blocking_recv() {
            if !engine.handle(e)? {
                break;
            }
        }
        Ok(())
    });
    let mut worker = worker;
    tokio::select! {r=&mut worker=>{r??;},_=async{let mut sig=tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()).unwrap();tokio::select!{_=sig.recv()=>{},_=tokio::signal::ctrl_c()=>{}}}=>{let _=tx.send(Event::Stop).await;worker.await??;}}
    for task in tasks {
        task.abort();
    }
    let _ = std::fs::remove_file(socket);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use execution::portfolio::Permissions;
    fn fixture(tag: &str) -> (Config, std::path::PathBuf) {
        let root =
            std::env::temp_dir().join(format!("b89-trader-test-{}-{tag}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let env = root.join("trading.env");
        std::fs::write(&env,format!("TRADING_PRIVATE_KEY={}\nINITIAL_STOCKS_ETH=0.057\nINITIAL_EXCHANGE_SHORT_ETH=0.057\n","01".repeat(32))).unwrap();
        std::fs::set_permissions(&env, std::fs::Permissions::from_mode(0o600)).unwrap();
        let mut c: Config =
            serde_json::from_str(include_str!("../../config/metric-trader-b89.json")).unwrap();
        c.credentials_file = env.to_str().unwrap().into();
        c.state_directory = root.join("state").to_str().unwrap().into();
        c.audit_file = root.join("audit.bin").to_str().unwrap().into();
        c.status_file = root.join("status.json").to_str().unwrap().into();
        c.executor = Some(format!("0x{}", "11".repeat(20)));
        c.executor_codehash = Some(format!("0x{}", "22".repeat(32)));
        (c, root)
    }
    fn sync(e: &mut Engine) -> Input {
        let now = now_ns();
        e.head = Some((10, [3; 32], now));
        e.hashes.insert(10, [3; 32]);
        Input::Synchronize {
            epoch: 7,
            anchor_number: 10,
            anchor_hash: format!("0x{}", hex::encode([3; 32])),
            executor_codehash: e.c.executor_codehash.clone().unwrap(),
            account: AccountSnapshot {
                nonce: 2,
                cash: Amount(100_000_000),
                positions: BTreeMap::from([("ETH".into(), Amount(57_000_000_000_000_000))]),
                native: Amount(1_000_000_000_000_000_000),
                permissions: BTreeMap::from([(
                    "ETH".into(),
                    Permissions {
                        executor_verified: true,
                        provider_access_verified: true,
                        base_allowance: Amount(u128::MAX),
                        quote_allowance: Amount(u128::MAX),
                    },
                )]),
                observed_ns: now,
            },
        }
    }
    fn observation() -> Observation {
        let now = now_ns();
        Observation {
            pool: address(POOL).unwrap(),
            epoch: 7,
            state_version: 1,
            state_valid: true,
            state_received_ns: now,
            bbo_received_ns: now,
            provider_valid_until_ns: now + 2_000_000_000,
            bid_e8: Amount(200_000_000_000),
            ask_e8: Amount(200_000_000_000),
            quantity: Amount(50_000_000_000_000_000),
            pool_bid_usdg: Amount(99_800_000),
            pool_ask_usdg: Amount(99_900_000),
        }
    }
    #[tokio::test]
    async fn standby_never_reserves_and_gap_invalidates() {
        let (c, root) = fixture("standby");
        let mut e = Engine::new(c, vec![], tokio::runtime::Handle::current()).unwrap();
        e.producer = true;
        let input = sync(&mut e);
        e.input(input).unwrap();
        let q = observation();
        e.bbo = Some(Bbo {
            recv: now_ns(),
            bid: q.bid_e8,
            ask: q.ask_e8,
        });
        e.input(Input::Quote { observation: q }).unwrap();
        e.decide().unwrap();
        assert_eq!(e.counts.get("standby_signals"), Some(&1));
        assert!(e.wallet.as_ref().unwrap().pending().is_none());
        e.input(Input::Gap {
            reason: "disconnect".into(),
        })
        .unwrap();
        assert!(e.account_epoch.is_none() && e.quote.is_none());
        e.decide().unwrap();
        assert_eq!(e.counts.get("standby_signals"), Some(&1));
        drop(e);
        std::fs::remove_dir_all(root).unwrap();
    }
    #[tokio::test]
    async fn cap_epoch_and_independent_bbo_enforced() {
        let (c, root) = fixture("bounds");
        let mut e = Engine::new(c, vec![], tokio::runtime::Handle::current()).unwrap();
        e.producer = true;
        let input = sync(&mut e);
        e.input(input).unwrap();
        let mut q = observation();
        q.quantity = Amount(51_000_000_000_000_000);
        e.bbo = Some(Bbo {
            recv: now_ns(),
            bid: q.bid_e8,
            ask: q.ask_e8,
        });
        e.input(Input::Quote { observation: q }).unwrap();
        e.decide().unwrap();
        assert!(!e.counts.contains_key("standby_signals"));
        let mut q = observation();
        q.epoch = 8;
        assert!(e.input(Input::Quote { observation: q }).is_err());
        e.bbo = None;
        e.quote = Some(observation());
        e.decide().unwrap();
        assert!(!e.counts.contains_key("standby_signals"));
        drop(e);
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn credential_permissions_and_exact_baseline() {
        let (c, root) = fixture("keys");
        let cr = c.credentials().unwrap();
        assert_eq!(cr.baseline.initial_base.0, 57_000_000_000_000_000);
        std::fs::set_permissions(&c.credentials_file, std::fs::Permissions::from_mode(0o644))
            .unwrap();
        assert!(c.credentials().is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn pilot_budget_cannot_silently_expand() {
        let (mut c, root) = fixture("config");
        c.additional_long_usdg = "500".into();
        assert!(c.validate().is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn binary_protocol_roundtrip() {
        let r = Input::Quote {
            observation: observation(),
        };
        let f = wire::frame(&serde_json::to_value(r).unwrap()).unwrap();
        let r: Input = serde_json::from_value(wire::parse(&f[4..]).unwrap()).unwrap();
        assert!(matches!(r, Input::Quote { .. }));
    }
}
