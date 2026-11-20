//! Concrete ABI for our minimal executor, derived from immutable order intent.
use super::{Intent, Side, codec};
use anyhow::{Result, ensure};
pub const TRADE_SIGNATURE: &str = "trade(address,bool,uint128,uint128,uint64)";
pub fn selector() -> [u8; 4] {
    codec::hash(TRADE_SIGNATURE.as_bytes())[..4]
        .try_into()
        .unwrap()
}
pub fn trade(pool: [u8; 20], intent: &Intent) -> Result<Vec<u8>> {
    ensure!(
        intent.quantity.0 > 0 && intent.quantity.0 <= i128::MAX as u128 && intent.limit_usdg.0 > 0,
        "invalid swap size/limit"
    );
    let mut args = codec::address(pool);
    args.extend(codec::word(u128::from(intent.side == Side::Buy)));
    args.extend(codec::word(intent.quantity.0));
    args.extend(codec::word(intent.limit_usdg.0));
    args.extend(codec::word((intent.valid_until_ns / 1_000_000_000) as u128));
    Ok(codec::call(TRADE_SIGNATURE, args))
}
/// No caller-supplied arbitrary calldata is accepted by the inventory engine.
pub fn transaction(
    pool: [u8; 20],
    executor: [u8; 20],
    intent: &Intent,
    nonce: u64,
    gas: u64,
    max_fee: u128,
    priority_fee: u128,
) -> Result<codec::Transaction> {
    ensure!(
        executor != [0; 20] && pool != [0; 20],
        "unconfigured executor/pool"
    );
    Ok(codec::Transaction {
        nonce,
        priority_fee,
        max_fee,
        gas,
        to: executor,
        value: 0,
        data: trade(pool, intent)?,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::execution::Amount;
    #[test]
    fn encodes_size_direction_limit_and_deadline() {
        let i = Intent {
            side: Side::Buy,
            opening: true,
            quantity: Amount(100),
            quote_usdg: Amount(200),
            limit_usdg: Amount(201),
            signal_ns: 10,
            valid_until_ns: 1_999_999_999,
            epoch: 1,
            state_version: 2,
        };
        let b = trade([7; 20], &i).unwrap();
        assert_eq!(b.len(), 164);
        assert_eq!(&b[..4], &selector());
        assert_eq!(codec::uint(&b[36..68]).unwrap(), 1);
        assert_eq!(codec::uint(&b[68..100]).unwrap(), 100);
        assert_eq!(codec::uint(&b[100..132]).unwrap(), 201);
        assert_eq!(codec::uint(&b[132..164]).unwrap(), 1);
    }
}
