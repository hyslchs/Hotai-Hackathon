from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterator

from pipeline.cleaning.contract import SOURCE_FIELDS, TAIPEI


def iter_synthetic_rows(count: int = 1000) -> Iterator[dict[str, str]]:
    if count < 1:
        raise ValueError("count must be positive")
    origin = datetime(2026, 2, 1, 8, 0, tzinfo=TAIPEI)
    for index in range(count):
        started = origin + timedelta(minutes=index * 7)
        ended = started + timedelta(minutes=12 + (index % 9))
        yield {
            "Id": str(900000000 + index),
            "RiderId": str(800000000 + (index % 37)),
            "OrderStartDateTime_UTC8": started.isoformat(),
            "OrderEndDateTime_UTC8": ended.isoformat(),
            "PickUpLatitude": f"{25.01 + (index % 10) / 1000:.6f}",
            "PickUpLongitude": f"{121.50 + (index % 10) / 1000:.6f}",
            "DropOffLatitude": f"{25.03 + (index % 13) / 1000:.6f}",
            "DropOffLongitude": f"{121.52 + (index % 13) / 1000:.6f}",
            "TravelTime": str(12 + (index % 9)),
            "TravelDistance": str(3000 + (index % 17) * 250),
            "OrderFormCreatedTime_UTC8": (started - timedelta(minutes=8)).isoformat(),
            "PickUpLocationType": "" if index % 3 else "synthetic_station",
            "DropOffLocationType": "" if index % 4 else "synthetic_food",
            "PaymentTotalRange": "[100,200]" if index % 2 else "[200,300]",
        }


def synthetic_header() -> tuple[str, ...]:
    return SOURCE_FIELDS

