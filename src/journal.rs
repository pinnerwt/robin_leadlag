use anyhow::{Context, Result, bail, ensure};
use serde_json::{Map, Value};
use std::io::{Read, Write};

pub const MAGIC: &[u8; 8] = b"RLLBIN\x01\n";
const MAX_FRAME: usize = 8 * 1024 * 1024;

fn count(out: &mut Vec<u8>, n: usize) -> Result<()> {
    out.extend(u32::try_from(n)?.to_le_bytes());
    Ok(())
}

fn string(out: &mut Vec<u8>, text: &str) -> Result<()> {
    count(out, text.len())?;
    out.extend(text.as_bytes());
    Ok(())
}

// Positional BBO records omit recurring field names and retain exact decimal text.
const LIVE_BBO: &[&str] = &[
    "symbol",
    "update_id",
    "tokyo_recv_ns",
    "bid",
    "ask",
    "bid_qty",
    "ask_qty",
    "ws_link",
    "relay_seq",
    "ohio_recv_ns",
    "relay_link",
];
const PROBE_BBO: &[&str] = &[
    "ms",
    "bid",
    "ask",
    "symbol",
    "update_id",
    "bid_qty",
    "ask_qty",
    "mono_ns",
    "recv_ns",
    "link",
    "epoch",
];

fn encode_bbo(out: &mut Vec<u8>, fields: &Map<String, Value>) -> Result<bool> {
    let (tag, keys) = match fields.get("kind").and_then(Value::as_str) {
        Some("binance_bbo") => (9, LIVE_BBO),
        Some("bbo") => (10, PROBE_BBO),
        _ => return Ok(false),
    };
    if fields
        .keys()
        .any(|key| key != "kind" && !keys.contains(&key.as_str()))
    {
        return Ok(false);
    }
    let mask = keys.iter().enumerate().fold(0u16, |mask, (i, key)| {
        mask | (u16::from(fields.contains_key(*key)) << i)
    });
    out.push(tag);
    out.extend(mask.to_le_bytes());
    for key in keys {
        if let Some(value) = fields.get(*key) {
            encode(out, value)?;
        }
    }
    Ok(true)
}

fn encode(out: &mut Vec<u8>, value: &Value) -> Result<()> {
    match value {
        Value::Null => out.push(0),
        Value::Bool(false) => out.push(1),
        Value::Bool(true) => out.push(2),
        Value::Number(n) => {
            if let Some(n) = n.as_u64() {
                out.push(3);
                out.extend(n.to_le_bytes());
            } else if let Some(n) = n.as_i64() {
                out.push(4);
                out.extend(n.to_le_bytes());
            } else {
                out.push(5);
                out.extend(n.as_f64().context("invalid number")?.to_le_bytes());
            }
        }
        Value::String(s) => {
            out.push(6);
            string(out, s)?;
        }
        Value::Array(items) => {
            out.push(7);
            count(out, items.len())?;
            for item in items {
                encode(out, item)?;
            }
        }
        Value::Object(items) => {
            if encode_bbo(out, items)? {
                return Ok(());
            }
            out.push(8);
            count(out, items.len())?;
            for (key, item) in items {
                string(out, key)?;
                encode(out, item)?;
            }
        }
    }
    Ok(())
}

fn read_bytes<const N: usize>(input: &mut &[u8]) -> Result<[u8; N]> {
    let mut bytes = [0; N];
    input.read_exact(&mut bytes)?;
    Ok(bytes)
}

fn read_count(input: &mut &[u8]) -> Result<usize> {
    Ok(u32::from_le_bytes(read_bytes(input)?) as usize)
}

fn read_string(input: &mut &[u8]) -> Result<String> {
    let n = read_count(input)?;
    let (text, rest) = input.split_at_checked(n).context("truncated string")?;
    *input = rest;
    Ok(std::str::from_utf8(text)?.to_owned())
}

fn decode(input: &mut &[u8], depth: usize) -> Result<Value> {
    ensure!(depth < 64, "journal nesting too deep");
    Ok(match read_bytes::<1>(input)?[0] {
        0 => Value::Null,
        1 => false.into(),
        2 => true.into(),
        3 => u64::from_le_bytes(read_bytes(input)?).into(),
        4 => i64::from_le_bytes(read_bytes(input)?).into(),
        5 => f64::from_le_bytes(read_bytes(input)?).into(),
        6 => read_string(input)?.into(),
        7 => {
            let n = read_count(input)?;
            ensure!(n <= input.len(), "truncated array");
            Value::Array(
                (0..n)
                    .map(|_| decode(input, depth + 1))
                    .collect::<Result<_>>()?,
            )
        }
        8 => {
            let n = read_count(input)?;
            ensure!(n <= input.len() / 5, "truncated object");
            Value::Object(
                (0..n)
                    .map(|_| Ok((read_string(input)?, decode(input, depth + 1)?)))
                    .collect::<Result<Map<_, _>>>()?,
            )
        }
        tag @ (9 | 10) => {
            let (kind, keys) = if tag == 9 {
                ("binance_bbo", LIVE_BBO)
            } else {
                ("bbo", PROBE_BBO)
            };
            let mask = u16::from_le_bytes(read_bytes(input)?);
            ensure!(mask >> keys.len() == 0, "invalid BBO field mask");
            let mut fields = Map::new();
            fields.insert("kind".into(), kind.into());
            for (i, key) in keys.iter().enumerate() {
                if mask & (1 << i) != 0 {
                    fields.insert((*key).into(), decode(input, depth + 1)?);
                }
            }
            Value::Object(fields)
        }
        _ => bail!("unknown journal field type"),
    })
}

pub fn frame(value: &Value) -> Result<Vec<u8>> {
    let mut frame = vec![0; 4];
    encode(&mut frame, value)?;
    let n = frame.len() - 4;
    ensure!(n <= MAX_FRAME, "record too large");
    frame[..4].copy_from_slice(&(n as u32).to_le_bytes());
    Ok(frame)
}

pub fn parse(mut payload: &[u8]) -> Result<Value> {
    let row = decode(&mut payload, 0)?;
    ensure!(payload.is_empty(), "trailing record bytes");
    Ok(row)
}

pub fn valid_size(n: usize) -> Result<()> {
    ensure!((1..=MAX_FRAME).contains(&n), "invalid record length");
    Ok(())
}

pub fn replay(mut input: impl Read, mut output: impl Write) -> Result<()> {
    let mut magic = [0; MAGIC.len()];
    input.read_exact(&mut magic)?;
    ensure!(&magic == MAGIC, "unsupported journal version");
    loop {
        let mut size = [0; 4];
        if input.read(&mut size[..1])? == 0 {
            break;
        }
        input.read_exact(&mut size[1..])?;
        let size = u32::from_le_bytes(size) as usize;
        valid_size(size)?;
        let mut data = vec![0; size];
        input.read_exact(&mut data)?;
        serde_json::to_writer(&mut output, &parse(&data)?)?;
        writeln!(output)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn compact_bbo_preserves_exact_decimals_and_optional_fields() {
        for row in [
            serde_json::json!({"kind":"binance_bbo","symbol":"SPCXBUSDT","update_id":u64::MAX,
                "bid":"135.27000000","ask_qty":"0.00000001","ohio_recv_ns":123}),
            serde_json::json!({"kind":"bbo","ms":12.75,"bid":"135.27000000","ask":"135.28000000"}),
        ] {
            let frame = super::frame(&row).unwrap();
            assert!(matches!(frame[4], 9 | 10));
            assert_eq!(super::parse(&frame[4..]).unwrap(), row);
        }
    }

    #[test]
    fn binary_roundtrip_and_truncation() {
        let row =
            serde_json::json!({"timestamp":u64::MAX,"bins":[-2,"123",null,true],"value":1.25});
        let frame = super::frame(&row).unwrap();
        assert_eq!(super::parse(&frame[4..]).unwrap(), row);
        let mut capture = super::MAGIC.to_vec();
        capture.extend(frame);
        let mut output = Vec::new();
        super::replay(&capture[..], &mut output).unwrap();
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&output).unwrap(),
            row
        );
        assert!(super::replay(&capture[..capture.len() - 1], &mut Vec::new()).is_err());
    }
}
