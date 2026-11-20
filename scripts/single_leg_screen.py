"""Same-pool single-leg execution screen using observed fills as price proxies."""
import argparse
import bisect
from collections import defaultdict
from datetime import datetime, timezone
import json
import statistics
import sys

POOLS = {
    "0xae117891108ee263fa57c52b89ab04945dfc0a5d",
    "0xaf2640f82a499abfcf143fec309f1d8953b4a3ab",
    "0x1e8fc442ad3606719f7016ded6c17b56c3ca7386",
}
NS = 1_000_000_000


def load():
    bbo, fills = [], defaultdict(list)
    for line in sys.stdin:
        row = json.loads(line)
        kind = row["kind"]
        if kind == "binance_bbo" and row["symbol"] == "ETHUSDT":
            bbo.append((row["ohio_recv_ns"], (float(row["bid"]) + float(row["ask"])) / 2))
        elif kind == "swap" and not row["log"]["removed"]:
            pool = row["log"]["address"].lower()
            if pool not in POOLS:
                continue
            swap = row["swap"]
            eth = int(swap["delta0_raw"]) / 1e18
            usdg = int(swap["delta1_raw"]) / 1e6
            if eth * usdg < 0:
                fills[pool].append((row["recv_ns"], "buy" if eth < 0 else "sell",
                                    abs(usdg / eth), abs(eth)))
    bbo.sort()
    for seq in fills.values():
        seq.sort()
    return bbo, fills


def compute(bbo, fills, size):
    times, prices = zip(*bbo)
    results = []
    for delay in (100, 150, 250, 500):
        eligible = defaultdict(list)
        for pool, seq in fills.items():
            for t, side, price, qty in seq:
                cut = t - delay * 1_000_000
                i = bisect.bisect_right(times, cut) - 1
                j = bisect.bisect_right(times, cut - NS // 2) - 1
                if j < 0 or i <= j or cut - times[i] > NS // 4 or cut - NS // 2 - times[j] > NS // 4:
                    continue
                move = (prices[i] / prices[j] - 1) * 10_000
                if qty >= size and (move > 0) == (side == "buy"):
                    eligible[pool, side].append((t, price, abs(move)))
        for pool in sorted(fills):
            for side in ("buy", "sell"):
                exits = [(t, p) for t, s, p, q in fills[pool] if s != side and q >= size]
                exit_times = [t for t, _ in exits]
                for threshold in (2, 5, 10):
                    signals = [x for x in eligible[pool, side] if x[2] >= threshold]
                    for hold_ms in (500, 1000, 3000):
                        trades = []
                        next_entry = -1
                        for t, p, _ in signals:
                            if t <= next_entry:
                                continue
                            i = bisect.bisect_left(exit_times, t + hold_ms * 1_000_000)
                            if i == len(exits) or exit_times[i] > t + (hold_ms + 1000) * 1_000_000:
                                continue
                            end, q = exits[i]
                            next_entry = end
                            pnl = (q - p) if side == "buy" else (p - q)
                            trades.append((pnl / p * 10_000, pnl * size))
                        bp = [x[0] for x in trades]
                        results.append(dict(pool=pool, entry_side=side, delay_ms=delay,
                            trigger_bp=threshold, hold_ms=hold_ms, entry_samples=len(signals),
                            round_trips=len(bp), median_bp=statistics.median(bp) if bp else None,
                            gross_positive=sum(x > 0 for x in bp), above_10bp=sum(x > 10 for x in bp),
                            gross_usdg=sum(x[1] for x in trades)))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=float, default=0.1)
    args = parser.parse_args()
    if args.size <= 0:
        parser.error("--size must be positive")
    bbo, fills = load()
    fmt = lambda ns: datetime.fromtimestamp(ns / NS, timezone.utc).isoformat()
    json.dump(dict(start_utc=fmt(bbo[0][0]), end_utc=fmt(bbo[-1][0]),
        size_weth=args.size, eth_bbo=len(bbo), fills={p:len(s) for p,s in fills.items()},
        screens=compute(bbo,fills,args.size)),sys.stdout,indent=2)
    print()


if __name__ == "__main__":
    main()
