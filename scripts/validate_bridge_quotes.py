"""Arbitrary-size quote isolation and oracle propagation in the offline bridge."""
import json
import time
from pathlib import Path
from cc1a_state_bridge import Bridge
seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
update=json.loads(Path('tests/fixtures/metric_weth_oracle_update.json').read_text())
with Bridge(seed,'captures/startup-v9-dependencies.json') as bridge:
    sizes=['0.02','0.1','0.00123456789']
    before=bridge.quotes(sizes)
    assert all('bid' in r and 'ask' in r for r in before),before
    start=time.perf_counter_ns();repeat=bridge.quotes(sizes);elapsed=time.perf_counter_ns()-start
    assert before==repeat,'quote simulations changed persistent state'
    bridge.update_oracle(update)
    after=bridge.quotes(sizes)
    assert all('bid' in r and 'ask' in r for r in after),after
    assert before!=after,'feed update did not change quotes'
    assert after==bridge.quotes(sizes),'post-update quotes changed state'
    # Oversized request may fail without invalidating the underlying state.
    unavailable=bridge.quotes(['1000000'])
    assert 'reason' in unavailable[0]
    assert bridge.valid and bridge.quotes(sizes)==after
Path('reports/amm/bridge-quote-validation.json').write_text(json.dumps(dict(
    purpose='Archived state plus isolated captured feed update, not historical replay or executable quotes',
    before=before,after=after,oversized=unavailable,
    repeated_three_size_wall_ns=elapsed,includes_python_ipc_and_clones=True),indent=2)+'\n')
print('arbitrary-size bid/ask, read-only repeat, feed propagation and oversize isolation passed')
print(f'three-size quote wall time: {elapsed/1e6:.1f} ms (experimental worker)')
