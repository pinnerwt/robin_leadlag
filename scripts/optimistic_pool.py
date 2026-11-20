"""Pool-scoped optimistic V3 follower. No RPC in the event reducer.
Input: decode_feed --with-raw JSONL. Output: append-only RLLBIN journal.
Background bootstrap is the only RPC worker. See OPTIMISTIC_POOL.md.
"""
import argparse
import collections
import copy
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from aqua_book import make_book
from tape import MAGIC, write_record


class Follower:
    def __init__(self, seed, sizes, emit, max_blocks=20000, registry=None):
        self.book = make_book(seed, registry, assume_success=True)
        self.sizes, self.emit, self.max_blocks = sizes, emit, max_blocks
        self.blocks = collections.deque()
        self.anchor = seed['anchor']['hash']
        self.started = False
        self.allow_seed_anchor = True
        self.generation = 0
        self.needs_sync = True
        self.emit(dict(kind='optimistic_checkpoint', seed=seed, registry=registry,
                       sizes=sizes, max_blocks=max_blocks, initial=True))

    def note(self, kind, **fields):
        self.emit(dict(kind=kind, observed_mono_ns=time.monotonic_ns(), **fields))

    def apply(self, book, row):
        invalid_before = set(book.invalid)
        touched = book.proposal(row)
        for pool in set(book.invalid) - invalid_before:
            self.note('optimistic_pool_invalid', pool=pool, reason=book.invalid[pool], tx=row['tx'])
            touched.append(pool)
        if row['tx'] in book.partial:
            notes = book.partial.pop(row['tx'])
            book.counts['partial_transactions'] += 1
            self.note('calldata_partial_decode', tx=row['tx'], to=row['to'], notes=notes,
                      generation=self.generation)
        # Validation queues belong to the old log-based audit, not the hot path.
        book.expected.clear()
        if row['tx'] in book.unsupported:
            reason = book.unsupported.pop(row['tx'])
            book.counts['coverage_gaps'] += 1
            self.note('calldata_coverage_gap', tx=row['tx'], to=row['to'], reason=reason,
                      generation=self.generation)
        return touched

    def publish(self, touched, row, cause):
        for pool in touched:
            for quote in self.book.quotes(pool, self.sizes, row):
                quote.update(phase='optimistic_live', timing='local_compute_complete',
                             available_mono_ns=time.monotonic_ns(),
                             available_ns=time.time_ns(),
                             available_clock='host_monotonic_ns',
                             source_clock='capture_elapsed_ns' if cause == 'calldata' else 'host_monotonic_ns',
                             source_mono_ns=row['mono_ns'], generation=self.generation,
                             assumption='calldata_success', cause=cause,
                             sync_required=self.needs_sync,
                             coverage_gaps_since_snapshot=self.book.counts['coverage_gaps'],
                             partial_transactions_since_snapshot=self.book.counts['partial_transactions'])
                self.emit(quote)

    def event(self, row):
        self.emit(dict(kind='optimistic_input', event=row))
        kind = row['kind']
        if kind == 'gap' and row.get('stream') != 'binance':
            self.blocks.clear()
            self.allow_seed_anchor = False
            self.needs_sync = True
            self.started = False
            self.note('optimistic_sync_required', reason='transport gap')
            return
        if kind == 'feed_block':
            seq = int(row['sequence'])
            if self.blocks and seq <= int(self.blocks[-1]['marker']['sequence']):
                if seq == int(self.blocks[-1]['marker']['sequence']) and row['block_hash'] == self.blocks[-1]['marker']['block_hash']:
                    return
                self.blocks.clear()
                self.allow_seed_anchor = False
                self.started = False
                self.needs_sync = True
            if self.blocks and (seq != int(self.blocks[-1]['marker']['sequence']) + 1 or
                                len(self.blocks[-1]['txs']) != self.blocks[-1]['marker']['transaction_count']):
                self.blocks.clear()
                self.allow_seed_anchor = False
                self.started = False
                self.needs_sync = True
                self.note('optimistic_sync_required', reason='sequence or transaction gap')
            self.blocks.append(dict(marker=row, txs=[]))
            while len(self.blocks) > self.max_blocks:
                self.blocks.popleft()
            if self.allow_seed_anchor and row['block_hash'] == self.anchor:
                self.allow_seed_anchor = False
                self.started = True
                self.needs_sync = False
            return
        if kind not in ('feed_tx', 'feed_system_tx'):
            return
        if not self.blocks or row.get('block_hash') != self.blocks[-1]['marker']['block_hash']:
            self.started = False
            self.needs_sync = True
            self.note('optimistic_sync_required', reason='transaction without block')
            return
        block = self.blocks[-1]
        if any(tx.get('tx') == row.get('tx') and tx['kind'] == kind for tx in block['txs']):
            return
        block['txs'].append(row)
        if self.started and row['block_hash'] != self.anchor and kind == 'feed_tx':
            touched = self.apply(self.book, row)
            self.publish(touched, row, 'calldata')

    def install(self, seed, registry=None):
        """Owner-thread atomic install: fixed block B + observed transactions after B."""
        index = next((i for i, b in enumerate(self.blocks)
                      if b['marker']['block_hash'] == seed['anchor']['hash']), None)
        if index is None:
            raise ValueError('snapshot anchor not in retained contiguous feed')
        blocks = list(self.blocks)
        anchor = blocks[index]
        if len(anchor['txs']) != anchor['marker']['transaction_count']:
            raise ValueError('snapshot anchor block is not complete yet')
        candidate = make_book(seed, registry, assume_success=True)
        if set(candidate.states) != set(self.book.states):
            raise ValueError('snapshot pool coverage changed')
        for block in blocks[index + 1:]:
            for row in block['txs']:
                if row['kind'] == 'feed_tx':
                    self.apply(candidate, row)
        changed = [pool for pool in candidate.states
                   if candidate.states[pool] != self.book.states[pool]
                   or candidate.invalid.get(pool) != self.book.invalid.get(pool)]
        self.book = candidate
        self.anchor = seed['anchor']['hash']
        self.started = True
        self.allow_seed_anchor = False
        self.needs_sync = False
        self.generation += 1
        self.note('optimistic_checkpoint', seed=seed, registry=registry,
                  generation=self.generation, changed_pools=changed, initial=False)
        now = dict(mono_ns=time.monotonic_ns(), recv_ns=time.time_ns(), tx=None)
        self.publish(list(candidate.states), now, 'reconciliation')
        return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('config')
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    output = open(cfg['output'], 'xb')
    output.write(MAGIC)
    def emit(row):
        write_record(output, row)
        output.flush()
    registry = json.loads(Path(cfg['registry']).read_text()) if cfg.get('registry') else None
    registry_template = json.loads(Path(cfg['registry_template']).read_text()) if cfg.get('registry_template') else registry
    follower = Follower(json.loads(Path(cfg['checkpoint']).read_text()),
                        cfg.get('sizes', ['0.02', '0.1']), emit,
                        cfg.get('max_buffer_blocks', 20000), registry)
    events = queue.Queue(maxsize=cfg.get('input_queue_size', 10000))
    results = queue.Queue()
    def reader():
        try:
            for line in sys.stdin:
                events.put(json.loads(line))
        except Exception as exc:
            events.put(dict(kind='gap', stream='decoder', reason=str(exc)))
        finally:
            events.put(None)
    threading.Thread(target=reader, daemon=True).start()
    stopped = threading.Event()
    process_lock = threading.Lock()
    sync_process = [None]
    def sync():
        try:
            with tempfile.TemporaryDirectory(prefix='pool-sync-') as directory:
                path = str(Path(directory) / 'snapshot.json')
                command = [part.replace('{output}', path) for part in cfg['sync_command']]
                with process_lock:
                    if stopped.is_set():return
                    process = subprocess.Popen(command, stdout=sys.stderr)
                    sync_process[0] = process
                try:
                    status = process.wait(timeout=cfg.get('sync_timeout_seconds', 600))
                    if status:raise ValueError('snapshot worker exit ' + str(status))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                    with process_lock:
                        sync_process[0] = None
                if stopped.is_set():return
                seed = json.loads(Path(path).read_text())
                # Mutable packed mappings must be refreshed at the SAME anchor.
                refreshed = None
                if registry_template:
                    from bootstrap_state import Bootstrap
                    from router_registry import refresh_registry
                    b = Bootstrap(cfg.get('rpc_url', 'https://rpc-robinhood.blockmachine.io'),
                                  interval=cfg.get('rpc_interval_seconds', 0.7))
                    refreshed = refresh_registry(registry_template, seed['anchor'], b.rpc, stopped)
                if cfg.get('aqua_template'):
                    if not refreshed:raise ValueError('Aqua checkpoint requires refreshed registry')
                    from bootstrap_aqua import refresh_aqua
                    template = json.loads(Path(cfg['aqua_template']).read_text())
                    seed['aqua'] = refresh_aqua(template, seed['anchor'], b.rpc, stopped)
                    # Reject incomplete dependency pins/anchors before queuing install.
                    make_book(seed, refreshed, assume_success=True)
                results.put((seed, refreshed, None))
        except Exception as exc:
            results.put((None, None, str(exc)))
    active = False
    pending = None
    next_sync = 0.0
    try:
        while True:
            now = time.monotonic()
            if not active and pending is None and now >= next_sync:
                threading.Thread(target=sync, daemon=True).start()
                active = True
            try:
                seed, refreshed_registry, error = results.get_nowait()
                active = False
                next_sync = now + cfg.get('sync_interval_seconds', 300)
                if error:
                    follower.note('optimistic_sync_failed', reason=error)
                else:
                    pending = (seed, refreshed_registry, now)
            except queue.Empty:
                pass
            try:
                row = events.get(timeout=0.05)
            except queue.Empty:
                row = False
            if row is None:
                break
            if row is not False:
                follower.event(row)
                if follower.needs_sync and not active and pending is None:
                    next_sync = min(next_sync, now + cfg.get('sync_retry_seconds', 5))
            if pending:
                try:
                    follower.install(pending[0], pending[1])
                    pending = None
                except ValueError as exc:
                    if now - pending[2] > cfg.get('anchor_wait_seconds', 15):
                        follower.note('optimistic_sync_rejected', reason=str(exc))
                        pending = None
                        next_sync = now + cfg.get('sync_retry_seconds', 5)
    finally:
        stopped.set()
        with process_lock:
            process = sync_process[0]
            if process is not None and process.poll() is None:
                process.terminate()
        output.close()


if __name__ == '__main__':
    main()
