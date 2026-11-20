// Adapted from /home/pgi/pons/rust-strategy/src/evm.rs.
//! Small, checked ABI and EIP-1559 codec. Amounts outside uint128 fail closed.
type Address = [u8; 20];
use anyhow::{Context, Result, ensure};
use sha3::{Digest, Keccak256};
pub fn hash(v: &[u8]) -> [u8; 32] {
    Keccak256::digest(v).into()
}
pub fn word(n: u128) -> Vec<u8> {
    let mut w = vec![0; 16];
    w.extend(n.to_be_bytes());
    w
}
pub fn address(a: Address) -> Vec<u8> {
    let mut w = vec![0; 12];
    w.extend(a);
    w
}
pub fn uint(w: &[u8]) -> Result<u128> {
    ensure!(
        w.len() == 32 && w[..16].iter().all(|b| *b == 0),
        "uint128 overflow/invalid word"
    );
    Ok(u128::from_be_bytes(w[16..].try_into()?))
}
pub fn bytes(v: &[u8]) -> Vec<u8> {
    let mut b = word(v.len() as u128);
    b.extend(v);
    b.resize(32 + v.len().div_ceil(32) * 32, 0);
    b
}
pub fn bytes_array(v: &[Vec<u8>]) -> Vec<u8> {
    let mut b = word(v.len() as u128);
    let mut tail = vec![];
    for x in v {
        b.extend(word((32 * v.len() + tail.len()) as u128));
        tail.extend(bytes(x));
    }
    b.extend(tail);
    b
}
pub fn call(sig: &str, args: Vec<u8>) -> Vec<u8> {
    let mut b = hash(sig.as_bytes())[..4].to_vec();
    b.extend(args);
    b
}
pub fn quantity(n: u128) -> String {
    format!("0x{n:x}")
}
pub fn parse_quantity(v: &serde_json::Value) -> Result<u128> {
    Ok(u128::from_str_radix(
        v.as_str()
            .context("RPC quantity missing")?
            .strip_prefix("0x")
            .context("quantity prefix")?,
        16,
    )?)
}
fn rlp_bytes(b: &[u8]) -> Vec<u8> {
    if b.len() == 1 && b[0] < 128 {
        return b.to_vec();
    }
    let mut out = rlp_len(b.len(), 0x80);
    out.extend(b);
    out
}
fn rlp_len(n: usize, offset: u8) -> Vec<u8> {
    if n < 56 {
        return vec![offset + n as u8];
    }
    let b = n.to_be_bytes();
    let b = &b[b.iter().position(|x| *x != 0).unwrap()..];
    let mut out = vec![offset + 55 + b.len() as u8];
    out.extend(b);
    out
}
fn rlp_int(n: u128) -> Vec<u8> {
    let b = n.to_be_bytes();
    rlp_bytes(&b[b.iter().position(|x| *x != 0).unwrap_or(16)..])
}
fn rlp_list(items: &[Vec<u8>]) -> Vec<u8> {
    let n = items.iter().map(Vec::len).sum();
    let mut out = rlp_len(n, 0xc0);
    for v in items {
        out.extend(v)
    }
    out
}
#[derive(Clone)]
pub struct Transaction {
    pub nonce: u64,
    pub priority_fee: u128,
    pub max_fee: u128,
    pub gas: u64,
    pub to: Address,
    pub value: u128,
    pub data: Vec<u8>,
}
impl Transaction {
    pub fn sign(&self, key: &k256::ecdsa::SigningKey) -> Result<Vec<u8>> {
        self.sign_target(key, false)
    }
    pub fn sign_creation(&self, key: &k256::ecdsa::SigningKey) -> Result<Vec<u8>> {
        ensure!(self.to == [0; 20], "creation target must be empty");
        self.sign_target(key, true)
    }
    fn sign_target(&self, key: &k256::ecdsa::SigningKey, creation: bool) -> Result<Vec<u8>> {
        ensure!(
            self.priority_fee <= self.max_fee && self.gas > 0,
            "invalid gas settings"
        );
        let mut fields = vec![
            rlp_int(4663),
            rlp_int(self.nonce as u128),
            rlp_int(self.priority_fee),
            rlp_int(self.max_fee),
            rlp_int(self.gas as u128),
            rlp_bytes(if creation { &[] } else { &self.to }),
            rlp_int(self.value),
            rlp_bytes(&self.data),
            vec![0xc0],
        ];
        let mut unsigned = vec![2];
        unsigned.extend(rlp_list(&fields));
        let (sig, rec) = key.sign_prehash_recoverable(&hash(&unsigned))?;
        ensure!(!rec.is_x_reduced(), "unsupported recovery id");
        fields.push(rlp_int(rec.to_byte() as u128));
        for b in sig.to_bytes().chunks(32) {
            fields.push(rlp_bytes(
                &b[b.iter().position(|v| *v != 0).unwrap_or(32)..],
            ));
        }
        let mut raw = vec![2];
        raw.extend(rlp_list(&fields));
        Ok(raw)
    }
}
pub fn wallet(key: &k256::ecdsa::SigningKey) -> Address {
    hash(&key.verifying_key().to_encoded_point(false).as_bytes()[1..])[12..]
        .try_into()
        .unwrap()
}

#[cfg(test)]
mod creation_tests {
 use super::*;
 use alloy_consensus::{TxEnvelope,Transaction as _};
 use alloy_eips::eip2718::Decodable2718;
 #[test]
 fn creation_has_empty_target_and_recovers_owner() {
  let key=k256::ecdsa::SigningKey::from_slice(&[7u8;32]).unwrap();
  let tx=Transaction{nonce:4,priority_fee:0,max_fee:1_000_000_000,gas:1_500_000,to:[0;20],value:0,data:vec![0x60,0]};
  let raw=tx.sign_creation(&key).unwrap();
  let decoded=TxEnvelope::decode_2718(&mut raw.as_slice()).unwrap();
  assert!(decoded.to().is_none());assert_eq!(decoded.nonce(),4);
  assert_eq!(decoded.recover_signer().unwrap().as_slice(),wallet(&key));
  let raw=tx.sign(&key).unwrap();
  assert!(TxEnvelope::decode_2718(&mut raw.as_slice()).unwrap().to().is_some());
 }
}
