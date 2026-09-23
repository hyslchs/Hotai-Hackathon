from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.cleaning.contract import ContractError, SOURCE_FIELDS, parse_source_row

EXPECTED_ROWS = 964_991
DEFAULT_CANDIDATES = (
    Path("data/raw/yoxi_數據資料.csv"),
    Path("data/yoxi_rawdata.csv"),
)


def choose_input() -> Path | None:
    configured = os.getenv("RAW_DATA_PATH")
    candidates = (Path(configured), *DEFAULT_CANDIDATES) if configured else DEFAULT_CANDIDATES
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else ROOT / candidate
        if resolved.is_file():
            return resolved
    return None


def main() -> int:
    source = choose_input()
    if source is None:
        print("BLOCKED: no raw CSV attachment found; contract fixture remains the only evidence")
        return 2

    row_count = 0
    malformed_width = 0
    contract_invalid = 0
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header != list(SOURCE_FIELDS):
                print(
                    "FAIL: source header does not match the documented 14-field contract",
                    file=sys.stderr,
                )
                return 1
            for row in reader:
                if not row or all(not cell.strip() for cell in row):
                    continue
                row_count += 1
                if len(row) != len(SOURCE_FIELDS):
                    malformed_width += 1
                    continue
                try:
                    parse_source_row(dict(zip(SOURCE_FIELDS, row)))
                except ContractError:
                    contract_invalid += 1
    except UnicodeDecodeError:
        print("FAIL: source is not UTF-8 compatible", file=sys.stderr)
        return 1

    print(f"source_file={source.relative_to(ROOT)}")
    print(f"observed_rows={row_count}")
    print(f"expected_rows_from_spec={EXPECTED_ROWS}")
    print(f"row_count_matches_spec={row_count == EXPECTED_ROWS}")
    print(f"rows_with_wrong_column_count={malformed_width}")
    print(f"rows_rejected_by_phase0_contract={contract_invalid}")
    print("scope=header, encoding, row shape, and contract parse only; no cleaning or output rewrite")

    return 0 if malformed_width == 0 and contract_invalid == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
