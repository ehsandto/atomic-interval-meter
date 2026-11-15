**Contribution type** Builder → Intelligent Contracts

**Title** AtomicIntervalMeter — Leap-Second Interval Arithmetic

**Notes / Description**

AtomicIntervalMeter measures elapsed SI seconds between UTC labels and advances or rewinds a timestamp by a signed duration. It represents the inserted label 23:59:60Z explicitly.

The leader and validators independently download the IERS and NIST leap-second tables. They parse every transition, verify the publisher checksums, require matching transition rows, and use the earlier expiry. Exact agreement on the normalized table and both publishers' metadata is required. The contract stores the agreed table by content digest. Callers select an immutable table ID. Labels outside its coverage revert.

StudioNet verified the import, a two-second interval across the 2016 insertion, forward and reverse navigation through 23:59:60Z, and rejection of a false leap label and dates outside coverage.

**Evidence**

- [Repository](https://github.com/ehsandto/atomic-interval-meter)
- [Deployed source](https://github.com/ehsandto/atomic-interval-meter/blob/881bf49198abc66538440d7c0b80324993bcf134/contracts/AtomicIntervalMeter.py)
- [StudioNet contract](https://explorer-studio.genlayer.com/address/0x5e97b6AadaCAafE31c6Dff4e491a9667ED82d49b)
- [Live proof matrix](https://github.com/ehsandto/atomic-interval-meter/blob/main/LIVE_PROOFS.md)
- [deploy](https://explorer-studio.genlayer.com/tx/0x9401cd1dff0e88cf7477e1e7d1a2526cf4b751e0961f783c98b115cbdd94852d)
- [import](https://explorer-studio.genlayer.com/tx/0xe1a727d79d6cfbf923174fc0e5f5df83d17c77873756c8838041172191399c10)
