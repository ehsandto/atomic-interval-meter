import ast
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contracts/AtomicIntervalMeter.py"
REFERENCE = json.loads((ROOT / "REFERENCE.json").read_text(encoding="utf-8"))
LAST_CHANGE = 3692217600


@pytest.fixture
def core():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if not isinstance(node, ast.ClassDef)
                 and not (isinstance(node, ast.ImportFrom) and node.module == "genlayer")]
    ns = {}
    exec(compile(tree, str(SOURCE), "exec"), ns)
    return ns


def document(source_index, rows=None, expires=None):
    meta = REFERENCE["sources"][source_index]
    rows = REFERENCE["rows"] if rows is None else rows
    expiry = meta["expires_ntp"] if expires is None else expires
    pairs = [f"{stamp}  {offset}" for stamp, offset in rows]
    fields = [str(meta["updated_ntp"]), str(expiry), *pairs]
    checksum = hashlib.sha1("".join("".join(fields).split()).encode("ascii")).hexdigest()
    if source_index == 0:
        checksum = " ".join(re.findall(r".{8}", checksum))
    return ("#$ " + fields[0] + "\n#@ " + fields[1] + "\n"
            + "\n".join(pairs) + "\n#h " + checksum + "\n").encode()


def test_two_publisher_formats_and_independent_reference(core):
    calls = []
    def fetch(url):
        calls.append(url)
        return SimpleNamespace(status=200, body=document(core["SOURCES"].index(url)))
    assert core["acquire"](fetch) == REFERENCE
    assert calls == list(core["SOURCES"])


@pytest.mark.parametrize("transform", [
    lambda s: s.replace(b"3692217600  37", b"3692217600  36"),
    lambda s: s.replace(b"3992312697", b"3992312698"),
    lambda s: s.split(b"#h")[0],
    lambda s: s + b"\n#@ 4023129600",
    lambda s: b"\xff" + s,
])
def test_rejects_corrupt_or_incomplete_files(core, transform):
    with pytest.raises(ValueError):
        core["parse_table"](transform(document(0)))


def test_agreement_requires_rows_even_with_valid_publisher_checksums(core):
    rows = REFERENCE["rows"][:-1]
    def fetch(url):
        ix = core["SOURCES"].index(url)
        return SimpleNamespace(status=200, body=document(ix, rows if ix else None))
    with pytest.raises(ValueError, match="tables disagree"):
        core["acquire"](fetch)


def test_effective_expiry_is_earlier_source_expiry(core):
    earlier = REFERENCE["expires_ntp"] - 86400
    def fetch(url):
        ix = core["SOURCES"].index(url)
        return SimpleNamespace(status=200, body=document(ix, expires=earlier if ix else None))
    assert core["acquire"](fetch)["expires_ntp"] == earlier


def test_across_all_real_positive_transitions(core):
    rows, expiry = REFERENCE["rows"], REFERENCE["expires_ntp"]
    epoch = datetime(1900, 1, 1)
    for effective, after in rows[1:]:
        midnight = epoch + timedelta(seconds=effective)
        preceding = (midnight - timedelta(seconds=1)).isoformat()
        labels = [preceding + "Z", preceding[:-2] + "60Z", midnight.isoformat() + "Z"]
        expected = [effective + after - 2, effective + after - 1, effective + after]
        assert [core["encode_utc"](rows, expiry, s) for s in labels] == expected
        assert [core["decode_utc"](rows, expiry, n) for n in expected] == labels


def test_negative_leap_second_and_no_duplicate_atomic_label(core):
    t = 2287785600
    expiry = t + 86400
    rows, _ = core["parse_table"](document(0, [[2272060800, 10], [t, 9]], expires=None))
    assert core["encode_utc"](rows, expiry, "1972-06-30T23:59:58Z") == t + 8
    assert core["decode_utc"](rows, expiry, t + 9) == "1972-07-01T00:00:00Z"
    with pytest.raises(ValueError, match="does not exist"):
        core["encode_utc"](rows, expiry, "1972-06-30T23:59:59Z")
    with pytest.raises(ValueError, match="does not exist"):
        core["encode_utc"](rows, expiry, "1972-06-30T23:59:60Z")


@pytest.mark.parametrize("label", [
    "1971-12-31T23:59:59Z", "2016-12-30T23:59:60Z", "2016-12-31T23:58:60Z",
    "2016-12-31T23:59:61Z", "2017-02-29T00:00:00Z", "2017-01-01T00:00:00+00:00",
    "2027-06-28T00:00:00Z",
])
def test_invalid_labels_and_coverage(core, label):
    with pytest.raises(ValueError):
        core["encode_utc"](REFERENCE["rows"], REFERENCE["expires_ntp"], label)


def test_direct_contract_consensus_and_interval_reads(direct_vm, direct_deploy):
    contract = direct_deploy(str(SOURCE))

    def install(replace=None):
        direct_vm.clear_mocks()
        for i, source in enumerate(REFERENCE["sources"]):
            direct_vm.mock_web(re.escape(source["url"]) + "$", {
                "method": "GET", "response": {"status": 200, "headers": {},
                                             "body": replace if i == 1 and replace else document(i)},
            })

    install()
    table = contract.import_table()
    assert contract.get_table(table) == REFERENCE
    assert contract.import_table() == table
    assert direct_vm.run_validator()
    forged = {**REFERENCE, "expires_ntp": REFERENCE["expires_ntp"] + 1}
    assert not direct_vm.run_validator(leader_result=json.dumps(forged, sort_keys=True, separators=(",", ":")))
    before, midnight = "2016-12-31T23:59:59Z", "2017-01-01T00:00:00Z"
    result = contract.measure(table, before, midnight)
    assert result == {"table_id": table, "start_atomic": LAST_CHANGE + 35, "end_atomic": LAST_CHANGE + 37,
                      "elapsed_seconds": 2, "offset_changes": [[LAST_CHANGE, 37]]}
    assert contract.advance(table, before, 1) == "2016-12-31T23:59:60Z"
    assert contract.advance(table, midnight, -2) == before
    with direct_vm.expect_revert("End precedes start"):
        contract.measure(table, midnight, before)
    with direct_vm.expect_revert("Unknown leap-second table"):
        contract.advance("0" * 64, midnight, 0)
    install(document(1, rows=REFERENCE["rows"][:-1]))
    assert not direct_vm.run_validator()
    with direct_vm.expect_revert("publisher evidence unavailable or inconsistent"):
        contract.import_table()
    assert contract.get_table(table) == REFERENCE
