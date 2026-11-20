"""Threshold-driven, same-pool replay using swap prices as execution proxies."""
import argparse
import bisect
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from single_leg_screen import NS, load

SIZE = 0.1
FRESH = NS


def market_events(bbo, fills):
    market = [(t, 0, p, "") for t, p in bbo]
    market += [(t, 1, p, side) for t, side, p, qty in fills if qty >= SIZE]
    market.sort()
    return market


def simulate(market, entry_bp, exit_bp, start_side, delay):
    # A later same-side observation proxies execution if the gap still clears.
    side = start_side
    quotes = {}
    mid = None
    pending = entry = None
    pnl = []
    orders = missed = 0
    for t, kind, price, observed_side in market:
        if pending is not None and t > pending + FRESH:
            pending = None
            missed += 1
        if kind == 0:
            mid = (t, price)
        else:
            quotes[observed_side] = (t, price)
        if mid is None or t - mid[0] > FRESH or side not in quotes:
            continue
        qt, quote = quotes[side]
        if t - qt > FRESH:
            continue
        gap = (mid[1] / quote - 1) * 10_000 if side == "buy" else (quote / mid[1] - 1) * 10_000
        threshold = entry_bp if entry is None else exit_bp
        if pending is not None:
            if kind == 1 and observed_side == side and t >= pending and gap >= threshold:
                if entry is None:
                    entry = (t, price)
                else:
                    gross = (price - entry[1]) if side == "sell" else (entry[1] - price)
                    pnl.append((gross / entry[1] * 10_000, gross * SIZE, (t-entry[0])/NS))
                    entry = None
                side = "sell" if side == "buy" else "buy"
                pending = None
            continue
        if gap >= threshold:
            pending = t + delay
            orders += 1
    return dict(signals=orders, expired_signals=missed, pending_at_end=pending is not None,
                open_entry=entry, round_trips=len(pnl), gross_usdg=sum(x[1] for x in pnl),
                median_bp=statistics.median(x[0] for x in pnl) if pnl else None,
                gross_positive=sum(x[0]>0 for x in pnl), above_10bp=sum(x[0]>10 for x in pnl),
                median_hold_s=statistics.median(x[2] for x in pnl) if pnl else None)


def load_universe():
    catalog = Path(__file__).resolve().parents[1] / "reports/metric-pools-over-10k.json"
    pools = {p["pool"].lower(): p for p in json.loads(catalog.read_text())["pools"]
             if p["chain_id"] == 4663}
    symbols = {address: ("ETHUSDT" if p["pair"] == "WETH/USDG"
                         else p["pair"].split("/")[0] + "BUSDT")
               for address, p in pools.items()}
    bbo, fills = defaultdict(list), defaultdict(list)
    for line in sys.stdin:
        row = json.loads(line)
        if row["kind"] == "binance_bbo":
            bbo[row["symbol"]].append((row["ohio_recv_ns"],
                                      (float(row["bid"]) + float(row["ask"])) / 2))
        elif row["kind"] == "swap" and not row["log"]["removed"]:
            address = row["log"]["address"].lower()
            if address not in pools:
                continue
            pool = pools[address]
            d0, d1 = pool["decimals"]
            swap = row["swap"]
            base = int(swap["delta0_raw"]) / 10**d0
            quote = int(swap["delta1_raw"]) / 10**d1
            if pool["tokens"][0].lower() == "0x5fc5360d0400a0fd4f2af552add042d716f1d168":
                base, quote = quote, base
            if base * quote < 0:
                fills[address].append((row["recv_ns"], "buy" if base < 0 else "sell",
                                       abs(quote / base), abs(base)))
    for series in (*bbo.values(), *fills.values()):
        series.sort()
    return pools, symbols, bbo, fills


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay-ms", type=int, default=200)
    parser.add_argument("--entry-bp", type=float)
    parser.add_argument("--exit-bp", type=float, action="append")
    parser.add_argument("--all-pools", action="store_true")
    args = parser.parse_args()
    if args.entry_bp is None and args.exit_bp is not None:
        parser.error("--exit-bp requires --entry-bp")
    thresholds = [(bp, bp) for bp in (2, 5, 10, 15, 20)]
    if args.entry_bp is not None:
        exits = args.exit_bp if args.exit_bp is not None else [2]
        if any(not 0 <= bp < args.entry_bp for bp in exits):
            parser.error("require 0 <= exit-bp < entry-bp")
        thresholds = [(args.entry_bp, bp) for bp in exits]
    if args.delay_ms < 0:
        parser.error("--delay-ms must be nonnegative")
    if args.all_pools:
        pools, symbols, bbo, fills = load_universe()
    else:
        eth, fills = load()
        bbo = {"ETHUSDT": eth}
        pools = {address: {"pair": "WETH/USDG"} for address in fills}
        symbols = dict.fromkeys(pools, "ETHUSDT")
    rows, coverage = [], []
    start = min(seq[0][0] for seq in bbo.values() if seq)
    end = max(seq[-1][0] for seq in bbo.values() if seq)
    for pool in sorted(pools):
        symbol = symbols[pool]
        seq, prices = fills.get(pool, []), bbo.get(symbol, [])
        pair = pools[pool]["pair"]
        coverage.append(dict(pool=pool, pair=pair, symbol=symbol,
                             swaps=len(seq), binance_ticks=len(prices),
                             size_eligible_swaps=sum(qty >= SIZE for _, _, _, qty in seq)))
        if not prices:
            continue
        market = market_events(prices, seq) if seq else []
        for entry_bp, exit_bp in thresholds:
            for side in ("buy", "sell"):
                rows.append(dict(pool=pool, pair=pair, entry_bp=entry_bp,
                                 exit_bp=exit_bp, start_side=side,
                                 **simulate(market, entry_bp, exit_bp, side,
                                            args.delay_ms * 1_000_000)))
    print(json.dumps(dict(size_base=SIZE, delay_ms=args.delay_ms, proxy_max_age_ms=1000,
                          first_bbo_ns=start, last_bbo_ns=end,
                          coverage=coverage, screens=rows), indent=2))


if __name__ == "__main__":
    main()
