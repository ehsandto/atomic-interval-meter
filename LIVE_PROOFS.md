# StudioNet proof matrix

[StudioNet contract](https://explorer-studio.genlayer.com/address/0x5e97b6AadaCAafE31c6Dff4e491a9667ED82d49b) · [Deployed source](https://github.com/ehsandto/atomic-interval-meter/blob/881bf49198abc66538440d7c0b80324993bcf134/contracts/AtomicIntervalMeter.py) · [Receipt data and live reads](PROOFS.json)

The deployed source matched the pinned commit with normalized SHA-256
`f34c4b20c13fbca5e8ebe7bc5583d1aea973cea6f73c259f36e0607a604053bd`. Both receipts had independent votes and majority
agreement. The imported table matched the independently downloaded
[reference data](REFERENCE.json), with 28 rows and exclusive
expiry `2027-06-28T00:00:00Z`.

Table ID: `317e1509e914fe242b31bf9bd53cc0295635451fc7ecf9d4a4ddbff4ebe9dcd7`.

| Transaction | Status | Agree votes / initial validators |
| --- | --- | --- |
| [deploy](https://explorer-studio.genlayer.com/tx/0x9401cd1dff0e88cf7477e1e7d1a2526cf4b751e0961f783c98b115cbdd94852d) | FINALIZED / SUCCESS | 3 / 5 |
| [import](https://explorer-studio.genlayer.com/tx/0xe1a727d79d6cfbf923174fc0e5f5df83d17c77873756c8838041172191399c10) | FINALIZED / SUCCESS | 3 / 5 |

The following were verified with read calls against the deployed contract.
The proof script encodes the arguments independently and checks each result.

| Read | Inputs after table ID | Result |
| --- | --- | --- |
| 2016 insertion | `2016-12-31T23:59:59Z`, `2017-01-01T00:00:00Z` | 2 SI seconds |
| advance into insertion | `2016-12-31T23:59:59Z`, `1` | `2016-12-31T23:59:60Z` |
| advance out of insertion | `2016-12-31T23:59:60Z`, `1` | `2017-01-01T00:00:00Z` |
| rewind to insertion | `2017-01-01T00:00:00Z`, `-1` | `2016-12-31T23:59:60Z` |
| two insertions | `2015-06-30T23:59:59Z`, `2017-01-01T00:00:00Z` | 47520003 SI seconds |
| ordinary second | `2017-01-01T00:00:00Z`, `2017-01-01T00:00:01Z` | 1 SI seconds |
| invalid leap label | `2016-12-30T23:59:60Z`, `0` | Reverted |
| expiry boundary | `2027-06-27T23:59:59Z`, `1` | Reverted |
| before coverage | `1971-12-31T23:59:59Z`, `1` | Reverted |

Local tests also simulate a deleted UTC second and check parser failures,
publisher disagreement, and a forged leader report.
