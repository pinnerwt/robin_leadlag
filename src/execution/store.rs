// Adapted from Pons execution_store.rs; dual-slot binary commit barrier.
//! Bounded crash-safe execution snapshots. Only the live writer owns this file.
//! Alternate preallocated slots avoid rename/directory-sync on every transaction.
use anyhow::{Context, Result, ensure};
use std::{
    fs::{File, OpenOptions},
    os::unix::fs::{FileExt, OpenOptionsExt},
    path::Path,
};

pub(crate) const NAME: &str = "metric-execution.slots";
const SLOT: usize = 256 * 1024;
const HEADER: usize = 56;
const MAGIC: &[u8; 8] = b"RLLXQ01\0";

fn record(generation: u64, payload: &[u8]) -> Result<Vec<u8>> {
    ensure!(
        payload.len() <= SLOT - HEADER,
        "execution snapshot exceeds slot capacity"
    );
    let mut bytes = Vec::with_capacity(HEADER + payload.len());
    bytes.extend_from_slice(MAGIC);
    bytes.extend_from_slice(&generation.to_le_bytes());
    bytes.extend_from_slice(&(payload.len() as u64).to_le_bytes());
    let mut checked = bytes.clone();
    checked.extend_from_slice(payload);
    bytes.extend_from_slice(&super::codec::hash(&checked));
    bytes.extend_from_slice(payload);
    Ok(bytes)
}
fn read_slot(file: &File, index: usize) -> Result<Option<(u64, Vec<u8>)>> {
    let offset = (index * SLOT) as u64;
    let mut header = [0; HEADER];
    file.read_exact_at(&mut header, offset)?;
    if &header[..8] != MAGIC {
        return Ok(None);
    }
    let generation = u64::from_le_bytes(header[8..16].try_into().unwrap());
    let length = u64::from_le_bytes(header[16..24].try_into().unwrap());
    if generation == 0 || length > (SLOT - HEADER) as u64 {
        return Ok(None);
    }
    let mut payload = vec![0; length as usize];
    file.read_exact_at(&mut payload, offset + HEADER as u64)?;
    let mut checked = header[..24].to_vec();
    checked.extend_from_slice(&payload);
    if super::codec::hash(&checked).as_slice() != &header[24..56] {
        return Ok(None);
    }
    Ok(Some((generation, payload)))
}
fn latest(file: &File) -> Result<(usize, u64, Vec<u8>)> {
    ensure!(
        file.metadata()?.len() == (2 * SLOT) as u64,
        "invalid execution slot file length"
    );
    let mut selected = None;
    for i in 0..2 {
        if let Some((generation, payload)) = read_slot(file, i)? {
            if selected
                .as_ref()
                .is_none_or(|(_, old, _)| generation > *old)
            {
                selected = Some((i, generation, payload));
            }
        }
    }
    selected.context("no valid execution snapshot slot")
}
pub(crate) fn read(root: &Path) -> Result<Vec<u8>> {
    Ok(latest(&File::open(root.join(NAME))?)?.2)
}
pub(crate) fn write(root: &Path, payload: &[u8]) -> Result<()> {
    let started = std::time::Instant::now();
    let path = root.join(NAME);
    if !path.exists() {
        // Initialization/migration only, before live admission. The visible file
        // always has at least one complete record; an incomplete tmp is ignored.
        std::fs::create_dir_all(root)?;
        let tmp = root.join("metric-execution.slots.tmp");
        let file = OpenOptions::new()
            .create(true)
            .mode(0o600)
            .truncate(true)
            .write(true)
            .open(&tmp)?;
        file.write_all_at(&vec![0; 2 * SLOT], 0)?;
        file.write_all_at(&record(1, payload)?, 0)?;
        file.sync_all()?;
        std::fs::rename(tmp, &path)?;
        File::open(root)?.sync_all()?;
    } else {
        let file = OpenOptions::new().read(true).write(true).open(&path)?;
        let (old_slot, generation, _) = latest(&file)?;
        let generation = generation
            .checked_add(1)
            .context("execution generation overflow")?;
        let bytes = record(generation, payload)?;
        file.write_all_at(&bytes, ((1 - old_slot) * SLOT) as u64)?;
        // The other slot remains valid through partial writes and crashes. Only
        // this barrier's success grants dispatch permission to the caller.
        file.sync_data()?;
    }
    if started.elapsed().as_millis() >= 10 {
        eprintln!(
            "{}",
            serde_json::json!({"event":"execution_store_slow_write",
            "bytes":payload.len(),"total_us":started.elapsed().as_micros()})
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn torn_next_generation_preserves_previous_commit_and_can_be_retried() {
        let root = std::env::temp_dir().join(format!("metric-slot-crash-{}", std::process::id()));
        write(&root, b"first").unwrap();
        write(&root, b"second").unwrap();
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(root.join(NAME))
            .unwrap();
        let next = record(3, b"third").unwrap();
        // Crash after header and only part of payload: checksum rejects it.
        file.write_all_at(&next[..HEADER + 2], 0).unwrap();
        file.sync_data().unwrap();
        assert_eq!(read(&root).unwrap(), b"second");
        write(&root, b"third").unwrap();
        assert_eq!(read(&root).unwrap(), b"third");
        assert_eq!(file.metadata().unwrap().len(), (2 * SLOT) as u64);
        assert!(write(&root, &vec![0; SLOT]).is_err());
        assert_eq!(read(&root).unwrap(), b"third");
        // Both corrupted slots fail closed, never fall back to obsolete files.
        file.write_all_at(b"broken!!", 0).unwrap();
        file.write_all_at(b"broken!!", SLOT as u64).unwrap();
        assert!(read(&root).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
}
