# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import hashlib
import json
import re
from bisect import bisect_right
from datetime import datetime, timedelta

from genlayer import TreeMap, gl

SOURCES = (
    "https://hpiers.obspm.fr/iers/bul/bulc/ntp/leap-seconds.list",
    "https://tf.nist.gov/leap-seconds.list",
)
EPOCH = datetime(1900, 1, 1)
BASE_ROW = [2272060800, 10]
DAY = 86400
MAX_NTP = (datetime(9999, 1, 1) - EPOCH).days * DAY


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def ntp(instant):
    delta = instant - EPOCH
    return delta.days * DAY + delta.seconds


def civil(seconds):
    return EPOCH + timedelta(seconds=seconds)


def parse_table(body):
    if not isinstance(body, bytes) or not 0 < len(body) <= 16384:
        raise ValueError("Missing or oversized leap-second file")
    metadata = {}
    rows = []
    for line in body.decode("utf-8").splitlines():
        line = line.strip(" \t")
        if not line:
            continue
        if line.startswith(("#$", "#@", "#h")):
            marker = line[:2]
            if marker in metadata:
                raise ValueError("Duplicate leap-second metadata")
            metadata[marker] = line[2:].strip(" \t")
        elif not line.startswith("#"):
            row = re.fullmatch(r"([1-9][0-9]{0,11})[ \t]+([1-9][0-9]{0,2})",
                               line.split("#", 1)[0].rstrip(" \t"))
            if not row or len(rows) == 128:
                raise ValueError("Malformed leap-second row")
            rows.append([int(row[1]), int(row[2])])

    if set(metadata) != {"#$", "#@", "#h"} or not rows or rows[0] != BASE_ROW:
        raise ValueError("Incomplete leap-second file")
    if any(not re.fullmatch(r"[1-9][0-9]{0,11}", metadata[k]) for k in ("#$", "#@")):
        raise ValueError("Malformed leap-second lifetime")
    updated, expires = int(metadata["#$"]), int(metadata["#@"])
    if not BASE_ROW[0] <= updated < expires <= MAX_NTP or rows[-1][0] >= expires:
        raise ValueError("Invalid leap-second lifetime")

    for (previous, previous_offset), (effective, offset) in zip(rows, rows[1:]):
        if not previous < effective < expires or effective % DAY or abs(offset - previous_offset) != 1:
            raise ValueError("Invalid leap-second transition")
        date = civil(effective)
        if date.day != 1 or date.month not in (1, 4, 7, 10):
            raise ValueError("Unexpected leap-second date")

    field = metadata["#h"].lower()
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{8}(?:[ \t]+[0-9a-f]{8}){4})", field):
        raise ValueError("Malformed publisher checksum")
    checksum = "".join(field.split())
    checksum_material = str(updated) + str(expires) + "".join(f"{t}{off}" for t, off in rows)
    if hashlib.sha1(checksum_material.encode("ascii")).hexdigest() != checksum:
        raise ValueError("Publisher checksum mismatch")
    return rows, {"updated_ntp": updated, "expires_ntp": expires, "file_sha1": checksum}


def acquire(fetch):
    rows = None
    sources = []
    for url in SOURCES:
        response = fetch(url)
        if response.status != 200:
            raise ValueError("Publisher unavailable")
        current, metadata = parse_table(response.body)
        if rows is not None and current != rows:
            raise ValueError("Publisher transition tables disagree")
        rows = current
        sources.append({"url": url, **metadata})
    return {
        "schema": "atomic-interval/v1",
        "rows": rows,
        "expires_ntp": min(source["expires_ntp"] for source in sources),
        "sources": sources,
    }


def encode_utc(rows, expires, label):
    parts = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T"
                         r"([0-9]{2}):([0-9]{2}):([0-9]{2})Z", label)
    if not parts:
        raise ValueError("Expected YYYY-MM-DDThh:mm:ssZ")
    year, month, day, hour, minute, second = map(int, parts.groups())
    mark = ntp(datetime(year, month, day, hour, minute, min(second, 59)))
    if not rows[0][0] <= mark < expires:
        raise ValueError("UTC label outside table coverage")
    index = bisect_right(rows, mark, key=lambda row: row[0]) - 1
    offset = rows[index][1]
    change = 0
    if index + 1 < len(rows) and rows[index + 1][0] == mark + 1:
        change = rows[index + 1][1] - offset
    if second == 60 and change == 1:
        return mark + offset + 1
    if second > 59 or change == -1:
        raise ValueError("UTC label does not exist in this table")
    return mark + offset


def decode_utc(rows, expires, instant):
    if not rows[0][0] + rows[0][1] <= instant < expires + rows[-1][1]:
        raise ValueError("Atomic time outside table coverage")
    index = bisect_right(rows, instant, key=lambda row: row[0] + row[1]) - 1
    offset = rows[index][1]
    if index + 1 < len(rows):
        effective, future = rows[index + 1]
        if future == offset + 1 and instant == effective + offset:
            return civil(effective - 1).isoformat()[:-2] + "60Z"
    return civil(instant - offset).isoformat() + "Z"


class AtomicIntervalMeter(gl.Contract):
    tables: TreeMap[str, str]

    def __init__(self):
        pass

    @gl.public.write
    def import_table(self) -> str:
        def evaluate():
            try:
                return canonical(acquire(gl.nondet.web.get))
            except Exception:
                raise gl.vm.UserError("Leap-second publisher evidence unavailable or inconsistent")

        def validate(leader):
            if not isinstance(leader, gl.vm.Return):
                return False
            try:
                return evaluate() == leader.calldata
            except Exception:
                return False

        agreed = gl.vm.run_nondet_unsafe(evaluate, validate)
        table_id = hashlib.sha256(agreed.encode("utf-8")).hexdigest()
        if table_id not in self.tables:
            self.tables[table_id] = agreed
        return table_id

    @gl.public.view
    def get_table(self, table_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{64}", table_id) or table_id not in self.tables:
            raise gl.vm.UserError("Unknown leap-second table")
        return json.loads(self.tables[table_id])

    @gl.public.view
    def measure(self, table_id: str, start_utc: str, end_utc: str) -> dict:
        table = self.get_table(table_id)
        rows, expires = table["rows"], table["expires_ntp"]
        try:
            start = encode_utc(rows, expires, start_utc)
            end = encode_utc(rows, expires, end_utc)
        except ValueError as error:
            raise gl.vm.UserError(str(error))
        if end < start:
            raise gl.vm.UserError("End precedes start")
        changes = [row for row in rows[1:] if start < row[0] + row[1] <= end]
        return {"table_id": table_id, "start_atomic": start, "end_atomic": end,
                "elapsed_seconds": end - start, "offset_changes": changes}

    @gl.public.view
    def advance(self, table_id: str, start_utc: str, seconds: int) -> str:
        table = self.get_table(table_id)
        rows, expires = table["rows"], table["expires_ntp"]
        try:
            start = encode_utc(rows, expires, start_utc)
            return decode_utc(rows, expires, start + seconds)
        except ValueError as error:
            raise gl.vm.UserError(str(error))
