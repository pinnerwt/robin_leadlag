//! Offline source-price timing extraction; not executable pool quotes.
#[path = "../src/journal.rs"]
mod journal;
#[path = "../src/nitro.rs"]
mod nitro;
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    fs::File,
    io::{self, BufWriter, Read, Write},
};
fn emit(w: &mut BufWriter<File>, t: f64, p: f64) -> Result<()> {
    w.write_all(&t.to_le_bytes())?;
    w.write_all(&p.to_le_bytes())?;
    Ok(())
}
fn main() -> Result<()> {
    let dir = std::env::args().nth(1).context("directory")?;
    let wall_clock = std::env::args().any(|a| a == "--wall-clock");
    let manifest: Vec<Value> =
        serde_json::from_reader(File::open(format!("{dir}/manifest.json"))?)?;
    let ids: HashMap<u8, usize> = manifest
        .iter()
        .enumerate()
        .map(|(i, p)| (p["word_id"].as_u64().unwrap() as u8, i))
        .collect();
    let symbols: HashMap<String, usize> = manifest
        .iter()
        .enumerate()
        .map(|(i, p)| (p["symbol"].as_str().unwrap().to_owned(), i))
        .collect();
    let mut x: Vec<_> = manifest
        .iter()
        .map(|p| {
            File::create(format!("{dir}/{}-x.bin", p["symbol"].as_str().unwrap()))
                .map(BufWriter::new)
        })
        .collect::<Result<_, _>>()?;
    let mut y: Vec<_> = manifest
        .iter()
        .map(|p| {
            File::create(format!("{dir}/{}-y.bin", p["symbol"].as_str().unwrap()))
                .map(BufWriter::new)
        })
        .collect::<Result<_, _>>()?;
    let mut input = io::BufReader::new(io::stdin().lock());
    let mut magic = [0; 8];
    input.read_exact(&mut magic)?;
    ensure!(&magic == journal::MAGIC, "magic");
    let mut seen = HashSet::new();
    let mut counts = vec![0u64; manifest.len()];
    let mut gaps = HashMap::<String, u64>::new();
    let mut failed = 0u64;
    loop {
        let mut len = [0; 4];
        if input.read(&mut len[..1])? == 0 {
            break;
        }
        input.read_exact(&mut len[1..])?;
        let n = u32::from_le_bytes(len) as usize;
        journal::valid_size(n)?;
        let mut raw = vec![0; n];
        input.read_exact(&mut raw)?;
        let mut r = journal::parse(&raw)?;
        if wall_clock {
            r["mono_ns"] = r["recv_ns"].clone();
        }
        let t = r["mono_ns"].as_u64().unwrap_or(0) as f64 / 1e6;
        match r["kind"].as_str().unwrap_or("") {
            "bbo" => {
                if let Some(&i) = r["symbol"].as_str().and_then(|s| symbols.get(s)) {
                    let b = r["bid"].as_str().context("bid")?.parse::<f64>()?;
                    let a = r["ask"].as_str().context("ask")?.parse::<f64>()?;
                    emit(
                        &mut x[i],
                        t,
                        if b > 0. && a >= b {
                            (a + b) / 2.
                        } else {
                            f64::NAN
                        },
                    )?;
                }
            }
            "gap" => {
                let stream = r["stream"].as_str().unwrap_or("unknown");
                *gaps.entry(stream.to_owned()).or_default() += 1;
                for w in x.iter_mut().chain(y.iter_mut()) {
                    emit(w, t, f64::NAN)?;
                }
            }
            "nitro_push" => {
                if let Some(relay) = r["relay_recv_ns"].as_u64() {
                    let delay = r["recv_ns"]
                        .as_u64()
                        .context("recv")?
                        .checked_sub(relay)
                        .context("clock inversion")?;
                    r["mono_ns"] = json!(
                        r["mono_ns"]
                            .as_u64()
                            .unwrap()
                            .checked_sub(delay)
                            .context("underflow")?
                    );
                }
                let txs = match nitro::transactions_without_sender(&r) {
                    Ok(t) => t,
                    Err(_) => {
                        failed += 1;
                        for w in y.iter_mut() {
                            emit(w, t, f64::NAN)?;
                        }
                        continue;
                    }
                };
                for tx in txs {
                    if !tx["to"].as_str().is_some_and(|a| {
                        a.eq_ignore_ascii_case("0xe844701934d9c6085b292e428f41b911cc0b3872")
                    }) {
                        continue;
                    }
                    let hash = tx["tx"].as_str().context("tx hash")?.to_owned();
                    if !seen.insert(hash) {
                        continue;
                    }
                    let d = hex::decode(
                        tx["data"]
                            .as_str()
                            .context("data")?
                            .trim_start_matches("0x"),
                    )?;
                    if d.first() != Some(&0) || (d.len() - 1) % 32 != 0 {
                        failed += 1;
                        for w in y.iter_mut() {
                            emit(w, t, f64::NAN)?;
                        }
                        continue;
                    }
                    let mut words: HashMap<usize, &[u8]> = HashMap::new();
                    for w in d[1..].chunks_exact(32) {
                        if let Some(&i) = ids.get(&w[31]) {
                            let old = words.entry(i).or_insert(w);
                            if w[24..31] > old[24..31] {
                                *old = w;
                            }
                        }
                    }
                    for (i, w) in words {
                        let raw = u32::from_be_bytes(w[..4].try_into()?);
                        let price = if w[4..6] == [255, 255] {
                            f64::NAN
                        } else {
                            ((raw & ((1 << 27) - 1)) as f64) * 2f64.powi((raw >> 27) as i32) / 1e8
                        };
                        emit(
                            &mut y[i],
                            tx["mono_ns"].as_u64().unwrap() as f64 / 1e6,
                            price,
                        )?;
                        counts[i] += 1;
                    }
                }
            }
            _ => {}
        }
    }
    serde_json::to_writer_pretty(
        File::create(format!("{dir}/extraction.json"))?,
        &json!({"provider_updates":counts,"gaps":gaps,"decode_failures":failed,"scope":"optimistic direct oracle source mid at relay arrival; not pool quotes"}),
    )?;
    Ok(())
}
