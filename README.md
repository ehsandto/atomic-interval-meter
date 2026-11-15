# AtomicIntervalMeter

AtomicIntervalMeter measures elapsed SI seconds between civil UTC timestamps
and advances or rewinds a timestamp by a signed count of SI seconds. It handles
`23:59:60Z` explicitly. The 2016 interval from `23:59:59Z` on December 31
to midnight on January 1 takes two seconds.

[StudioNet proof matrix](LIVE_PROOFS.md) · [Submission text](SUBMISSION.md)

## Consensus

`import_table()` is permissionless and takes no caller evidence. The leader
and each validator fetch the IERS and NIST leap-second lists over HTTPS.
They parse the transition rows and validity fields, check each publisher's
checksum, require identical transition rows, and choose the earlier expiry.
The callback requires exact canonical JSON equality, including both sets of
publisher metadata. Agreement stores the table by SHA-256 of the normalized
report. Repeated imports of the same report reuse the same key.

| Method | Result |
| --- | --- |
| `import_table()` | Content ID of the agreed schedule |
| `get_table(id)` | All transition rows, publisher metadata, and exclusive UTC expiry |
| `measure(id, start, end)` | Atomic endpoint coordinates, elapsed seconds, and offset changes effective after the start through the end |
| `advance(id, start, seconds)` | UTC label reached after adding signed SI seconds |

Callers explicitly choose an immutable table ID. Dates are strict UTC labels
with whole seconds. The supported UTC interval runs from January 1, 1972 to
the earlier publisher expiry, exclusive. Invalid labels and out-of-coverage
queries revert. The arithmetic supports the deletion of `23:59:59Z` if both
publishers ever agree on a negative leap transition. The implementation uses
unsmeared UTC and integer arithmetic. Atomic coordinates count seconds from
the conventional coordinate origin of 1900-01-01T00:00:00 TAI.

The contract trusts the publishers for leap-second scheduling. The SHA-1
fields check the files for corruption. HTTPS, dual publication, and GenLayer
consensus establish which schedule the contract used. An older table can
still answer historical queries inside its coverage. The contract computes
time from the timestamps supplied and the agreed reference table.

[IERS leap-second list](https://hpiers.obspm.fr/iers/bul/bulc/ntp/leap-seconds.list) ·
[NIST leap-second documentation](https://www.nist.gov/pml/time-and-frequency-division/time-realization/leap-seconds)

```sh
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
genvm-lint check contracts/AtomicIntervalMeter.py
```

`REFERENCE.json` records the normalized publisher data fetched independently
of the contract. To verify existing StudioNet receipts and readbacks using
the pinned SDK, install with `npm ci` and run
`node scripts/prove.mjs <source-commit> --verify-only` with `PROOFS.json`
present.
