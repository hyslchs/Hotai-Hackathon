from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

SOURCE_FIELDS: tuple[str, ...] = (
    "Id",
    "RiderId",
    "OrderStartDateTime_UTC8",
    "OrderEndDateTime_UTC8",
    "PickUpLatitude",
    "PickUpLongitude",
    "DropOffLatitude",
    "DropOffLongitude",
    "TravelTime",
    "TravelDistance",
    "OrderFormCreatedTime_UTC8",
    "PickUpLocationType",
    "DropOffLocationType",
    "PaymentTotalRange",
)

_FARE_RE = re.compile(
    r"^\[\s*([0-9]+(?:\.[0-9]+)?)\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*\]$"
)


class ContractError(ValueError):
    """Raised when a source row violates the Phase 0 boundary."""


@dataclass(frozen=True)
class FareRange:
    raw: str
    lower_exclusive: Decimal
    upper_inclusive: Decimal
    midpoint: Decimal


@dataclass(frozen=True)
class TripRecord:
    trip_id: int
    rider_id: int
    started_at: datetime
    ended_at: datetime
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    travel_time_min: int
    travel_distance_m: int
    ordered_at: datetime
    pickup_poi_text: str | None
    dropoff_poi_text: str | None
    fare: FareRange


def validate_columns(columns: Sequence[str | None]) -> None:
    normalized = tuple("" if column is None else column for column in columns)
    if normalized != SOURCE_FIELDS:
        raise ContractError(
            "source columns do not match the 14-field contract; "
            f"expected {len(SOURCE_FIELDS)} ordered fields"
        )


def parse_datetime(value: str, field_name: str) -> datetime:
    text = value.strip()
    if not text:
        raise ContractError(f"{field_name} is empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field_name} is not a supported datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    else:
        parsed = parsed.astimezone(TAIPEI)
    return parsed


def parse_fare_range(value: str) -> FareRange:
    raw = value.strip()
    match = _FARE_RE.fullmatch(raw)
    if match is None:
        raise ContractError("PaymentTotalRange must look like [lower,upper]")
    try:
        lower = Decimal(match.group(1))
        upper = Decimal(match.group(2))
    except InvalidOperation as exc:
        raise ContractError("PaymentTotalRange contains a non-numeric bound") from exc
    if upper <= lower:
        raise ContractError("PaymentTotalRange must have a positive width")
    lower_exclusive_value = lower + Decimal("1")
    midpoint = (lower_exclusive_value + upper) / Decimal("2")
    return FareRange(
        raw=raw,
        lower_exclusive=lower_exclusive_value,
        upper_inclusive=upper,
        midpoint=midpoint,
    )


def _int(value: str, field_name: str, *, nonnegative: bool = False) -> int:
    try:
        parsed = int(value.strip())
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field_name} is not an integer") from exc
    if nonnegative and parsed < 0:
        raise ContractError(f"{field_name} must be nonnegative")
    return parsed


def _float(value: str, field_name: str) -> float:
    try:
        parsed = float(value.strip())
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field_name} is not numeric") from exc
    if parsed != parsed:
        raise ContractError(f"{field_name} must be finite")
    return parsed


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def parse_source_row(row: Mapping[str, str | None]) -> TripRecord:
    validate_columns(tuple(row.keys()))
    return TripRecord(
        trip_id=_int(row["Id"] or "", "Id"),
        rider_id=_int(row["RiderId"] or "", "RiderId"),
        started_at=parse_datetime(row["OrderStartDateTime_UTC8"] or "", "OrderStartDateTime_UTC8"),
        ended_at=parse_datetime(row["OrderEndDateTime_UTC8"] or "", "OrderEndDateTime_UTC8"),
        pickup_lat=_float(row["PickUpLatitude"] or "", "PickUpLatitude"),
        pickup_lng=_float(row["PickUpLongitude"] or "", "PickUpLongitude"),
        dropoff_lat=_float(row["DropOffLatitude"] or "", "DropOffLatitude"),
        dropoff_lng=_float(row["DropOffLongitude"] or "", "DropOffLongitude"),
        travel_time_min=_int(row["TravelTime"] or "", "TravelTime", nonnegative=True),
        travel_distance_m=_int(row["TravelDistance"] or "", "TravelDistance", nonnegative=True),
        ordered_at=parse_datetime(
            row["OrderFormCreatedTime_UTC8"] or "",
            "OrderFormCreatedTime_UTC8",
        ),
        pickup_poi_text=_optional_text(row["PickUpLocationType"]),
        dropoff_poi_text=_optional_text(row["DropOffLocationType"]),
        fare=parse_fare_range(row["PaymentTotalRange"] or ""),
    )

