//! Route one immutable tape into independently checkpointed extraction processes.
#[path = "../src/journal.rs"]
mod journal;
use anyhow::{Context, Result, ensure};
use serde_json::Value;
use std::{
    fs::File,
    io::{self, Read, Write},
    process::{Command, Stdio},
};
fn main() -> Result<()> {
    let manifest = std::env::args().nth(1).context("segments manifest")?;
    let segments: Vec<Value> = serde_json::from_reader(File::open(manifest)?)?;
    let mut input = io::BufReader::new(io::stdin().lock());
    let mut magic = [0; 8];
    input.read_exact(&mut magic)?;
    ensure!(&magic == journal::MAGIC, "magic");
    let mut session = Vec::new();
    let mut index = 0;
    let mut child: Option<std::process::Child> = None;
    loop {
        let mut len = [0; 4];
        if input.read(&mut len[..1])? == 0 {
            break;
        }
        input.read_exact(&mut len[1..])?;
        let n = u32::from_le_bytes(len) as usize;
        journal::valid_size(n)?;
        let mut bytes = vec![0; n];
        input.read_exact(&mut bytes)?;
        let row = journal::parse(&bytes)?;
        if row["kind"] == "session" {
            session.extend_from_slice(&len);
            session.extend_from_slice(&bytes);
            continue;
        }
        let t = row["mono_ns"].as_u64().unwrap_or(0);
        while index < segments.len() && t >= segments[index]["end_ns"].as_u64().unwrap() {
            if let Some(mut c) = child.take() {
                drop(c.stdin.take());
                ensure!(c.wait()?.success(), "extract child failed");
                eprintln!("finished {}", index);
            }
            index += 1;
        }
        if index >= segments.len() {
            continue;
        }
        if t < segments[index]["extract_start_ns"].as_u64().unwrap() {
            continue;
        }
        if child.is_none() {
            let dir = segments[index]["directory"].as_str().unwrap();
            let log = File::create(format!("{dir}/extract.log"))?;
            let mut c = Command::new("target/release/examples/prepare_recovery_causal")
                .arg(dir)
                .stdin(Stdio::piped())
                .stdout(Stdio::null())
                .stderr(log)
                .spawn()?;
            let w = c.stdin.as_mut().unwrap();
            w.write_all(&magic)?;
            w.write_all(&session)?;
            child = Some(c);
        }
        let w = child.as_mut().unwrap().stdin.as_mut().unwrap();
        w.write_all(&len)?;
        w.write_all(&bytes)?;
    }
    if let Some(mut c) = child {
        drop(c.stdin.take());
        ensure!(c.wait()?.success(), "extract child failed");
    }
    Ok(())
}
