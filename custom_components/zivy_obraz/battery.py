from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

from homeassistant.util import dt as dt_util

BATTERY_CHARGE_THRESHOLD_VOLTS = 0.15
BATTERY_CHARGE_MAX_STAT_VOLTAGE = 4.20
BATTERY_CHARGE_MIN_DAILY_SAMPLES = 3
BATTERY_CHARGE_COOLDOWN_DAYS = 2
BATTERY_CHARGE_HISTORY_DAYS = 14
BATTERY_CHARGE_ROBUST_SAMPLE_COUNT = 3


@dataclass
class BatteryChargeState:
    """Derived battery charge diagnostics for one panel."""

    last_charged: datetime | None = None
    daily_high: float | None = None
    daily_low: float | None = None
    daily_samples: int = 0
    excluded_daily_samples: int = 0
    previous_daily_high: float | None = None
    status: str = "warming_up"
    _samples_by_day: dict[date, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _excluded_samples_by_day: dict[date, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    _last_sample_id: str | None = None
    _last_detected_day: date | None = None


class BatteryChargeTracker:
    """Track battery voltage trends and infer likely charge days."""

    def __init__(self) -> None:
        """Initialize the tracker."""
        self._states: dict[str, BatteryChargeState] = {}

    def state_for(self, mac: str) -> BatteryChargeState:
        """Return charge state for a panel."""
        return self._states.setdefault(mac, BatteryChargeState())

    def restore_last_charged(self, mac: str, value: Any) -> None:
        """Restore the last charged timestamp from Home Assistant state restore."""
        if value is None:
            return

        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value))
            except (TypeError, ValueError):
                return

        self.state_for(mac).last_charged = parsed

    def process_device(self, mac: str, device_data: dict[str, Any]) -> None:
        """Process one panel payload."""
        value = device_data.get("battery_volts")
        if value is None:
            return

        try:
            voltage = float(value)
        except (TypeError, ValueError):
            return

        sample_time = self._parse_sample_time(device_data.get("last_contact"))
        last_contact = device_data.get("last_contact")
        sample_id = f"{last_contact}:{voltage}" if last_contact is not None else ""
        self.process_voltage(
            mac,
            voltage,
            sample_time or dt_util.now(),
            sample_id=sample_id or None,
        )

    def process_voltage(
        self,
        mac: str,
        voltage: float,
        now: datetime,
        *,
        sample_id: str | None = None,
    ) -> None:
        """Record a voltage sample and update charge diagnostics."""
        state = self.state_for(mac)
        if sample_id is not None and state._last_sample_id == sample_id:
            return

        state._last_sample_id = sample_id
        current_day = dt_util.as_local(now).date()
        if voltage > BATTERY_CHARGE_MAX_STAT_VOLTAGE:
            state._excluded_samples_by_day[current_day] += 1
        else:
            state._samples_by_day[current_day].append(voltage)
        self._prune_history(state, current_day)
        self._update_state(state, current_day, now)

    def _prune_history(self, state: BatteryChargeState, current_day: date) -> None:
        """Keep only recent daily samples."""
        first_day = current_day - timedelta(days=BATTERY_CHARGE_HISTORY_DAYS)
        for sample_day in list(state._samples_by_day):
            if sample_day < first_day:
                state._samples_by_day.pop(sample_day, None)
        for sample_day in list(state._excluded_samples_by_day):
            if sample_day < first_day:
                state._excluded_samples_by_day.pop(sample_day, None)

    def _update_state(
        self,
        state: BatteryChargeState,
        current_day: date,
        now: datetime,
    ) -> None:
        """Recalculate robust daily stats and charge status."""
        current_samples = state._samples_by_day.get(current_day, [])
        state.daily_samples = len(current_samples)
        state.excluded_daily_samples = state._excluded_samples_by_day[current_day]
        state.daily_high = self._robust_high(current_samples)
        state.daily_low = self._robust_low(current_samples)
        state.previous_daily_high = self._previous_daily_high(state, current_day)

        if state.daily_high is None:
            state.status = "insufficient_samples"
            return

        if state.previous_daily_high is None:
            state.status = "baseline"
            return

        if self._in_cooldown(state, current_day):
            state.status = "cooldown"
            return

        increase = state.daily_high - state.previous_daily_high
        if increase >= BATTERY_CHARGE_THRESHOLD_VOLTS:
            state.last_charged = now
            state._last_detected_day = current_day
            state.status = "charge_detected"
            return

        state.status = "idle"

    def _previous_daily_high(
        self,
        state: BatteryChargeState,
        current_day: date,
    ) -> float | None:
        """Return robust high from the latest valid previous day."""
        previous_days = (
            sample_day
            for sample_day in sorted(state._samples_by_day, reverse=True)
            if sample_day < current_day
        )
        for sample_day in previous_days:
            daily_high = self._robust_high(state._samples_by_day[sample_day])
            if daily_high is not None:
                return daily_high
        return None

    def _in_cooldown(self, state: BatteryChargeState, current_day: date) -> bool:
        """Return whether a recent charge detection is still in cooldown."""
        if state._last_detected_day is None:
            return False

        return (
            current_day - state._last_detected_day
        ).days < BATTERY_CHARGE_COOLDOWN_DAYS

    def _robust_high(self, samples: list[float]) -> float | None:
        """Return a daily high derived from multiple top samples."""
        if len(samples) < BATTERY_CHARGE_MIN_DAILY_SAMPLES:
            return None

        top_samples = sorted(samples, reverse=True)[:BATTERY_CHARGE_ROBUST_SAMPLE_COUNT]
        return round(float(median(top_samples)), 2)

    def _robust_low(self, samples: list[float]) -> float | None:
        """Return a daily low derived from multiple bottom samples."""
        if len(samples) < BATTERY_CHARGE_MIN_DAILY_SAMPLES:
            return None

        bottom_samples = sorted(samples)[:BATTERY_CHARGE_ROBUST_SAMPLE_COUNT]
        return round(float(median(bottom_samples)), 2)

    def _parse_sample_time(self, value: Any) -> datetime | None:
        """Parse a device contact timestamp for battery sample bucketing."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        try:
            return datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
