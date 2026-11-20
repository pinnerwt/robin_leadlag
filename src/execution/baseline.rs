//! Exact token-unit baselines: inventory sold below baseline is relative short exposure.
use super::{Amount, Config, Intent, Inventory, Observation, Side, decide, micro_ceil};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Baseline {
    pub initial_base: Amount,
    pub declared_exchange_short: Amount,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Exposure {
    pub direction: String,
    pub relative_quantity: Amount,
    pub chain_available_to_sell: Amount,
    pub maximum_relative_short: Amount,
    pub declared_hedged_net_direction: String,
    pub declared_hedged_net_quantity: Amount,
}
fn difference(a: u128, b: u128) -> (String, Amount) {
    if a >= b {
        (if a == b { "flat" } else { "long" }.into(), Amount(a - b))
    } else {
        ("short".into(), Amount(b - a))
    }
}
impl Baseline {
    pub fn exposure(&self, base: Amount, reserved_sell: Amount) -> Result<Exposure> {
        ensure!(reserved_sell.0 <= base.0, "reservation exceeds inventory");
        let (direction, relative_quantity) = difference(base.0, self.initial_base.0);
        let (declared_hedged_net_direction, declared_hedged_net_quantity) =
            difference(base.0, self.declared_exchange_short.0);
        Ok(Exposure {
            direction,
            relative_quantity,
            chain_available_to_sell: Amount(base.0 - reserved_sell.0),
            maximum_relative_short: self.initial_base,
            declared_hedged_net_direction,
            declared_hedged_net_quantity,
        })
    }
}
/// Decimal token quantity, no exponent, sign, rounding or floating-point conversion.
pub fn parse_quantity(s: &str, decimals: u32) -> Result<Amount> {
    ensure!(decimals <= 36 && !s.is_empty(), "invalid quantity");
    let mut parts = s.split('.');
    let whole = parts.next().unwrap();
    let frac = parts.next().unwrap_or("");
    ensure!(
        parts.next().is_none()
            && !whole.is_empty()
            && whole.bytes().all(|b| b.is_ascii_digit())
            && frac.bytes().all(|b| b.is_ascii_digit())
            && frac.len() <= decimals as usize,
        "invalid decimal quantity"
    );
    let scale = 10u128.checked_pow(decimals).context("decimal overflow")?;
    let value = whole
        .parse::<u128>()?
        .checked_mul(scale)
        .and_then(|n| {
            n.checked_add(if frac.is_empty() {
                0
            } else {
                frac.parse::<u128>()
                    .ok()?
                    .checked_mul(10u128.checked_pow(decimals - frac.len() as u32)?)?
            })
        })
        .context("quantity overflow")?;
    Ok(Amount(value))
}
/// Read only the explicit inventory keys; never execute .env shell expressions or expose secrets.
pub fn load(text: &str, tickers: &BTreeMap<String, u32>) -> Result<BTreeMap<String, Baseline>> {
    let mut vars = BTreeMap::new();
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let line = line.strip_prefix("export ").unwrap_or(line);
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let key = key.trim();
        if !key.starts_with("INITIAL_STOCKS_") && !key.starts_with("INITIAL_EXCHANGE_SHORT_") {
            continue;
        }
        let value = value.trim();
        let value = if value.len() >= 2
            && ((value.starts_with('"') && value.ends_with('"'))
                || (value.starts_with('\'') && value.ends_with('\'')))
        {
            &value[1..value.len() - 1]
        } else {
            value
        };
        ensure!(
            vars.insert(key.to_owned(), value.to_owned()).is_none(),
            "duplicate baseline key {key}"
        );
    }
    tickers
        .iter()
        .map(|(ticker, decimals)| {
            ensure!(
                !ticker.is_empty()
                    && ticker
                        .bytes()
                        .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit()),
                "invalid ticker"
            );
            let quantity = vars
                .get(&format!("INITIAL_STOCKS_{ticker}"))
                .with_context(|| format!("missing INITIAL_STOCKS_{ticker}"))?;
            let hedge = vars
                .get(&format!("INITIAL_EXCHANGE_SHORT_{ticker}"))
                .with_context(|| {
                    format!("missing INITIAL_EXCHANGE_SHORT_{ticker}; explicitly set 0 if unhedged")
                })?;
            Ok((
                ticker.clone(),
                Baseline {
                    initial_base: parse_quantity(quantity, *decimals)
                        .with_context(|| format!("invalid stock quantity for {ticker}"))?,
                    declared_exchange_short: parse_quantity(hedge, *decimals)
                        .with_context(|| format!("invalid hedge quantity for {ticker}"))?,
                },
            ))
        })
        .collect()
}
/// Closing quantities may not cross zero. The cap is additional long notional above fixed baseline.
/// At zero, both sides are independently eligible; the caller arbitrates a single wallet reservation.
pub fn decide_relative(
    c: &Config,
    b: &Baseline,
    inv: &Inventory,
    side: Side,
    o: &Observation,
    now: u64,
) -> Result<Option<Intent>> {
    let closing = match side {
        Side::Buy => inv.base.0 < b.initial_base.0,
        Side::Sell => inv.base.0 > b.initial_base.0,
    };
    if inv.base.0 != b.initial_base.0 && !closing {
        return Ok(None);
    }
    if closing {
        let gap = inv.base.0.abs_diff(b.initial_base.0);
        if o.quantity.0 > gap {
            return Ok(None);
        }
    }
    let mut c = c.clone();
    c.entry_side = if closing {
        match side {
            Side::Buy => Side::Sell,
            Side::Sell => Side::Buy,
        }
    } else {
        side
    };
    c.max_position_usdg = Amount(
        micro_ceil(b.initial_base.0, o.ask_e8.0, c.base_decimals)?
            .checked_add(c.max_position_usdg.0)
            .context("baseline cap overflow")?,
    );
    decide(&c, inv, closing, o, now)
}
/// Maximum exact base quantity to quote. Cash is the wallet's globally available USDG.
pub fn quantities(
    c: &Config,
    b: &Baseline,
    inv: &Inventory,
    ask_e8: Amount,
) -> Result<BTreeMap<String, Amount>> {
    ensure!(ask_e8.0 > 0, "zero reference ask");
    let scale = revm::primitives::U256::from(10).pow(revm::primitives::U256::from(c.base_decimals))
        * revm::primitives::U256::from(100);
    let to_base = |cash: u128| -> Result<u128> {
        (revm::primitives::U256::from(cash) * scale / revm::primitives::U256::from(ask_e8.0))
            .try_into()
            .map_err(|_| anyhow::anyhow!("quantity overflow"))
    };
    let cash = inv.cash.0.saturating_sub(c.gas_cost_usdg.0);
    let buy = if inv.base.0 < b.initial_base.0 {
        (b.initial_base.0 - inv.base.0).min(to_base(cash)?)
    } else if inv.base.0 == b.initial_base.0 {
        to_base(cash.min(c.max_position_usdg.0))?
    } else {
        0
    };
    let sell = if inv.base.0 > b.initial_base.0 {
        inv.base.0 - b.initial_base.0
    } else if inv.base.0 == b.initial_base.0 {
        inv.base.0
    } else {
        0
    };
    Ok(BTreeMap::from([
        ("buy".into(), Amount(buy)),
        ("sell".into(), Amount(sell)),
    ]))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_env_and_no_shell_execution() {
        let t = BTreeMap::from([("NVDA".into(), 18)]);
        let b=load("SECRET=ignored\nINITIAL_STOCKS_NVDA=3.000000000000000001\nINITIAL_EXCHANGE_SHORT_NVDA='3'",&t).unwrap();
        assert_eq!(b["NVDA"].initial_base.0, 3_000_000_000_000_000_001);
        assert!(parse_quantity("$(id)", 18).is_err());
        assert!(parse_quantity("1e3", 18).is_err());
        assert!(parse_quantity("-1", 18).is_err());
        assert!(parse_quantity("0.0000001", 6).is_err());
        assert!(load("INITIAL_STOCKS_NVDA=3", &t).is_err());
    }
    #[test]
    fn relative_short_is_bounded_by_real_inventory() {
        let b = Baseline {
            initial_base: Amount(300),
            declared_exchange_short: Amount(300),
        };
        let e = b.exposure(Amount(200), Amount(50)).unwrap();
        assert_eq!(e.direction, "short");
        assert_eq!(e.relative_quantity, Amount(100));
        assert_eq!(e.chain_available_to_sell, Amount(150));
        assert_eq!(e.maximum_relative_short, Amount(300));
        assert!(b.exposure(Amount(10), Amount(11)).is_err());
    }
}
