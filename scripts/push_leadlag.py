"""Compare pushed SPCXB BBO and hash-matched SPCX oracle updates."""
import bisect
import json
import math
import statistics
import sys


def returns(points, max_gap):
    points = sorted(dict(points).items())
    return [(a, b, math.log(q / p))
            for (a, p), (b, q) in zip(points, points[1:])
            if b - a <= max_gap]


def scan(binance, oracle, start, end):
    x = returns([(t, p) for t, p in binance if start <= t <= end], 5000)
    y = returns([(t, p) for t, p in oracle if start <= t <= end], 15000)
    norm = math.sqrt(sum(r*r for _, _, r in x) * sum(r*r for _, _, r in y))
    if not norm:
        return {"oracle_returns": len(y), "peak_ms": None}
    starts = [a for a, _, _ in x]
    ends = [b for _, b, _ in x]
    prefix = [0.]
    for _, _, r in x:
        prefix.append(prefix[-1]+r)
    curve = []
    for shift in range(-5000, 5001, 50):
        contrast = sum(r * (prefix[bisect.bisect_left(starts, b-shift)] -
                            prefix[bisect.bisect_right(ends, a-shift)])
                       for a, b, r in y) / norm
        curve.append([shift, contrast])
    peak, value = max(curve, key=lambda r: abs(r[1]))
    return dict(oracle_returns=len(y), binance_returns=len(x), peak_ms=peak,
                peak_contrast=value, zero_contrast=curve[100][1], curve=curve)


def blocked_validation(binance, oracle, start, end, folds):
    # Trim by the maximum candidate shift so shifted return pairs cannot
    # straddle a train/test boundary.
    width = (end - start) / folds
    curves = [scan(binance, oracle, start + i * width + 5000,
                   start + (i + 1) * width - 5000) for i in range(folds)]
    results = []
    zero = 100
    for i, test in enumerate(curves):
        result = {"fold": i + 1, "oracle_returns": test["oracle_returns"]}
        train = [c["curve"] for j, c in enumerate(curves) if j != i and "curve" in c]
        if train and "curve" in test:
            scores = [statistics.mean(c[j][1] for c in train) for j in range(len(train[0]))]
            best = max(range(len(scores)), key=lambda j: (scores[j], -abs(j - zero)))
            lag, value = test["curve"][best]
            result.update(lag_ms=lag, held_out_contrast=value,
                          delta_vs_zero=value - test["zero_contrast"])
        results.append(result)
    return results


def impulse_response(binance, oracle, start, end):
    """Measure oracle movement after distinct Binance mid moves of at least 2 bp."""
    oracle = sorted(oracle)
    oracle_times = [t for t, _ in oracle]
    binance_times = [t for t, _ in binance]
    observations = {200: [], 1000: [], 5000: [], 10000: []}
    last_signal = -math.inf
    for t, price in binance:
        if t < start or t + 10000 > end or t - last_signal < 10000:
            continue
        before = bisect.bisect_right(binance_times, t - 1000) - 1
        anchor = bisect.bisect_right(oracle_times, t) - 1
        if min(before, anchor) < 0 or t - binance_times[before] > 2000:
            continue
        move = math.log(price / binance[before][1]) * 10000
        if abs(move) < 2 or t - oracle_times[anchor] > 15000:
            continue
        last_signal = t
        for horizon, values in observations.items():
            after = bisect.bisect_right(oracle_times, t + horizon) - 1
            values.append(math.copysign(1, move) *
                          math.log(oracle[after][1] / oracle[anchor][1]) * 10000)
    return {h: dict(n=len(v), aligned=sum(x > 0 for x in v),
                    opposite=sum(x < 0 for x in v), zero=sum(x == 0 for x in v),
                    median_signed_bp=statistics.median(v) if v else None)
            for h, v in observations.items()}


def stats(values):
    values = sorted(values)
    return (dict(n=len(values), p50=statistics.median(values),
                 p90=values[math.ceil(len(values)*.9)-1])
            if values else dict(n=0))


def main():
    rows = [json.loads(line) for line in sys.stdin]
    bbo = [(r["ms"], (float(r["bid"])+float(r["ask"]))/2)
           for r in rows if r["kind"] == "bbo" and r.get("symbol", "SPCXBUSDT") == "SPCXBUSDT" and r.get("ms", -1) >= 5000]
    matches = [r for r in rows if r["kind"] == "match" and r["hash_verified"]
               and r["decoded"] and r["feed_ms"] >= 5000]
    if not bbo:
        raise SystemExit("no usable Binance BBO")
    start, end = min(t for t, _ in bbo), max(t for t, _ in bbo)
    report = dict(window_ms=[start,end], binance_bbo=len(bbo),
                  summaries=[r for r in rows if r["kind"] == "summary"], oracles={})
    for name in ("compressed","pyth"):
        events = [r for r in matches if r["oracle"] == name]
        mid = (start+end)/2
        stages = {}
        for stage in ("feed_ms","log_ms","ready_ms"):
            oracle = [(r[stage], r["price_e8"]) for r in events if r["price_e8"] > 0]
            stages[stage] = dict(full=scan(bbo,oracle,start,end),
                                 first=scan(bbo,oracle,start,mid),
                                 second=scan(bbo,oracle,mid,end),
                                 blocked={k: blocked_validation(bbo, oracle, start, end, k)
                                          for k in (3, 5, 10)})
        report["oracles"][name] = dict(
            stages=stages,
            impulse_response=impulse_response(sorted(bbo),
                [(r["feed_ms"], r["price_e8"]) for r in events if r["price_e8"] > 0],
                start, end),
            feed_to_log_ms=stats([r["log_ms"]-r["feed_ms"] for r in events]),
            feed_to_ready_ms=stats([r["ready_ms"]-r["feed_ms"] for r in events]),
            join_ms=stats([r["ready_ms"]-max(r["log_ms"],r["feed_ms"]) for r in events]))
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
