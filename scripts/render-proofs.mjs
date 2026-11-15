import fs from 'node:fs';
import assert from 'node:assert/strict';

const proof = JSON.parse(fs.readFileSync('PROOFS.json', 'utf8'));
const github = 'https://github.com/ehsandto/atomic-interval-meter';
const explorer = 'https://explorer-studio.genlayer.com';
assert(proof.verified && proof.source.source_match);
assert.equal(proof.transactions.length, 2);
assert.equal(Object.keys(proof.views).length, 9);
assert(proof.transactions.every(({receipt}) => receipt.status === 'FINALIZED' &&
  receipt.committed && receipt.execution === 'SUCCESS' && receipt.consensus === 'MAJORITY_AGREE' &&
  receipt.leader_only === false && receipt.agree_votes >= 2));

const deployment = `[StudioNet contract](${explorer}/address/${proof.address})`;
const source = `[Deployed source](${github}/blob/${proof.source_commit}/contracts/AtomicIntervalMeter.py)`;
const transactions = proof.transactions.map(({step, hash, receipt}) => ({
  link: `[${step}](${explorer}/tx/${hash})`,
  status: `${receipt.status} / ${receipt.execution}`,
  votes: `${receipt.agree_votes} / ${receipt.initial_validators}`,
}));
const views = Object.entries(proof.views).map(([name, view]) => {
  let result = 'Reverted';
  if (view.method === 'measure') result = `${view.value.elapsed_seconds} SI seconds`;
  if (typeof view.value === 'string') result = `\`${view.value}\``;
  return `| ${name} | ${view.args.slice(1).map(x => `\`${x}\``).join(', ')} | ${result} |`;
});
const reference = proof.table;
const expires = new Date(Date.UTC(1900, 0, 1) + reference.expires_ntp * 1000)
  .toISOString().replace('.000Z', 'Z');

fs.writeFileSync('LIVE_PROOFS.md', `# StudioNet proof matrix

${deployment} · ${source} · [Receipt data and live reads](PROOFS.json)

The deployed source matched the pinned commit with normalized SHA-256
\`${proof.source.sha256}\`. Both receipts had independent votes and majority
agreement. The imported table matched the independently downloaded
[reference data](REFERENCE.json), with ${reference.rows.length} rows and exclusive
expiry \`${expires}\`.

Table ID: \`${proof.table_id}\`.

| Transaction | Status | Agree votes / initial validators |
| --- | --- | --- |
${transactions.map(x => `| ${x.link} | ${x.status} | ${x.votes} |`).join('\n')}

The following were verified with read calls against the deployed contract.
The proof script encodes the arguments independently and checks each result.

| Read | Inputs after table ID | Result |
| --- | --- | --- |
${views.join('\n')}

Local tests also simulate a deleted UTC second and check parser failures,
publisher disagreement, and a forged leader report.
`);

const notes = `AtomicIntervalMeter measures elapsed SI seconds between UTC labels and advances or rewinds a timestamp by a signed duration. It represents the inserted label 23:59:60Z explicitly.

The leader and validators independently download the IERS and NIST leap-second tables. They parse every transition, verify the publisher checksums, require matching transition rows, and use the earlier expiry. Exact agreement on the normalized table and both publishers' metadata is required. The contract stores the agreed table by content digest. Callers select an immutable table ID. Labels outside its coverage revert.

StudioNet verified the import, a two-second interval across the 2016 insertion, forward and reverse navigation through 23:59:60Z, and rejection of a false leap label and dates outside coverage.`;
assert(notes.length <= 1000);
fs.writeFileSync('SUBMISSION.md', `**Contribution type** Builder → Intelligent Contracts

**Title** AtomicIntervalMeter — Leap-Second Interval Arithmetic

**Notes / Description**

${notes}

**Evidence**

- [Repository](${github})
- ${source}
- ${deployment}
- [Live proof matrix](${github}/blob/main/LIVE_PROOFS.md)
${transactions.map(x => '- ' + x.link).join('\n')}
`);
