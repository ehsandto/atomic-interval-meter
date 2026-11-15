import fs from 'node:fs';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {rpc, receipt, source, read, digest, denied} from './check.mjs';

const code = 'contracts/AtomicIntervalMeter.py';
const publisher = {name: 'studio-proof-deployer', address: '0x7a413BB4AB62E31d62d4cD9efC8C8a8Dae37FB42'};
const journal = 'PROOFS.json';
const commit = process.argv[2];
const verifyOnly = process.argv.includes('--verify-only');
assert(/^[a-f0-9]{40}$/.test(commit ?? ''));
const proof = fs.existsSync(journal)
  ? JSON.parse(fs.readFileSync(journal, 'utf8'))
  : {network: 'StudioNet', source_commit: commit, transactions: []};
assert.equal(proof.source_commit, commit);
const save = () => fs.writeFileSync(journal, JSON.stringify(proof, null, 2) + '\n');

function send(args, signer, entry) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['scripts/run-cli.cjs', ...args], {
      windowsHide: true,
      env: {...process.env, AIM_TEST_ACCOUNT: signer.name},
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let pending = '';
    child.stderr.resume();
    child.stdout.on('data', chunk => {
      const lines = (pending + chunk.toString()).split(/\r?\n/);
      pending = lines.pop();
      for (const line of lines) {
        const matched = /^BROADCAST_HASH (0x[0-9a-f]{64})$/i.exec(line);
        if (matched) {
          entry.hash = matched[1];
          save();
          console.log(entry.step, entry.hash);
        }
      }
    });
    child.on('error', reject);
    child.on('close', resolve);
  });
}

async function transaction(step, args, signer, expected = 'SUCCESS', message) {
  let entry = proof.transactions.find(item => item.step === step);
  if (!entry) {
    assert(!verifyOnly, 'Verification requires an original broadcast journal');
    const nonce = await rpc('eth_getTransactionCount', [signer.address, 'latest']);
    assert.equal(await rpc('eth_getTransactionCount', [signer.address, 'pending']), nonce);
    entry = {step, args, signer: signer.address, nonce};
    proof.transactions.push(entry);
    save();
    await send(args, signer, entry);
  }
  assert.deepEqual(entry.args, args);
  assert.equal(entry.signer, signer.address);
  assert(entry.hash, 'Broadcast status unknown. Inspect account history before any retry.');
  entry.receipt = await receipt(entry.hash, expected, message);
  save();
  assert.equal(entry.receipt.committed, expected === 'SUCCESS');
  const native = await rpc('eth_getTransactionByHash', [entry.hash]);
  assert.equal(native.from_address.toLowerCase(), signer.address.toLowerCase());
  assert.equal(BigInt(native.nonce), BigInt(entry.nonce));
  assert.equal(BigInt(native.value), 0n);
  console.log(step, entry.receipt.status, entry.receipt.execution);
  return entry.receipt.address;
}

const reference = JSON.parse(fs.readFileSync('REFERENCE.json', 'utf8'));
const tableId = digest(reference);
const ntpEpoch = Date.UTC(1900, 0, 1);
const nominal = label => (Date.parse(label) - ntpEpoch) / 1000;
const format = n => new Date(ntpEpoch + n * 1000).toISOString().replace('.000Z', 'Z');

assert.equal(await rpc('eth_chainId', []), '0xf22f');
proof.address = await transaction('deploy', ['deploy', '--contract', code], publisher);
proof.source = await source(proof.address);
save();
const to = await transaction('import', ['write', proof.address, 'import_table'], publisher);
assert.equal(to.toLowerCase(), proof.address.toLowerCase());
proof.table_id = tableId;
proof.table = await read(proof.address, 'get_table', [tableId]);
assert.deepEqual(proof.table, reference);
proof.views ??= {};
save();

async function view(name, method, args, expected) {
  const value = await read(proof.address, method, [tableId, ...args]);
  assert.deepEqual(value, expected, name);
  proof.views[name] = {method, args: [tableId, ...args], value};
  save();
  console.log(name, JSON.stringify(value));
}

async function rejection(name, method, args) {
  assert(await denied(proof.address, method, [tableId, ...args]), name);
  proof.views[name] = {method, args: [tableId, ...args], reverted: true};
  save();
  console.log(name, 'reverted');
}

const before = '2016-12-31T23:59:59Z';
const inserted = '2016-12-31T23:59:60Z';
const after = '2017-01-01T00:00:00Z';
const t = nominal(after);
await view('2016 insertion', 'measure', [before, after], {
  table_id: tableId, start_atomic: t + 35, end_atomic: t + 37,
  elapsed_seconds: 2, offset_changes: [[t, 37]],
});
await view('advance into insertion', 'advance', [before, 1], inserted);
await view('advance out of insertion', 'advance', [inserted, 1], after);
await view('rewind to insertion', 'advance', [after, -1], inserted);

const prior = '2015-06-30T23:59:59Z';
await view('two insertions', 'measure', [prior, after], {
  table_id: tableId, start_atomic: nominal(prior) + 35, end_atomic: t + 37,
  elapsed_seconds: t - nominal(prior) + 2, offset_changes: [[nominal(prior) + 1, 36], [t, 37]],
});
const next = '2017-01-01T00:00:01Z';
await view('ordinary second', 'measure', [after, next], {
  table_id: tableId, start_atomic: t + 37, end_atomic: t + 38,
  elapsed_seconds: 1, offset_changes: [],
});

await rejection('invalid leap label', 'advance', ['2016-12-30T23:59:60Z', 0]);
await rejection('expiry boundary', 'advance', [format(reference.expires_ntp - 1), 1]);
await rejection('before coverage', 'advance', ['1971-12-31T23:59:59Z', 1]);

const history = await rpc('sim_getTransactionsForAddress', [proof.address]);
assert.deepEqual(history.map(t => t.hash).sort(), proof.transactions.map(t => t.hash).sort());
proof.verified = true;
save();
