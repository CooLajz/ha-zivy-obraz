from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

BATTERY_CHARGE_THRESHOLD_VOLTS = 0.15
BATTERY_CHARGE_MAX_STAT_VOLTAGE = 4.20
BATTERY_CHARGE_BASELINE_DAYS = 3
BATTERY_CHARGE_COOLDOWN_DAYS = 2
BATTERY_CHARGE_HISTORY_DAYS = 30


@dataclass
class BatteryChargeState:
    """Derived battery charge diagnostics for one panel."""

    last_charged: datetime | None = None
    voltage_max: float | None = None
    voltage_min: float | None = None
    daily_average: float | None = None
    daily_samples: int = 0
    excluded_daily_samples: int = 0
    previous_average: float | None = None
    stored_days: int = 0
    valid_baseline_days: int = 0
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

    def last_detected_day_for(self, mac: str) -> date | None:
        """Return the last day when charging was detected for a panel."""
        return self.state_for(mac)._last_detected_day

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

    def restore_voltage_max(self, mac: str, value: Any) -> None:
        """Restore the maximum observed battery voltage."""
        voltage = self._parse_voltage(value)
        if voltage is not None:
            self.state_for(mac).voltage_max = voltage

    def restore_voltage_min(self, mac: str, value: Any) -> None:
        """Restore the minimum observed battery voltage."""
        voltage = self._parse_voltage(value)
        if voltage is not None:
            self.state_for(mac).voltage_min = voltage

    def process_device(self, mac: str, device_data: dict[str, Any]) -> bool:
        """Process one panel payload."""
        value = device_data.get("battery_volts")
        if value is None:
            return False

        voltage = self._parse_voltage(value)
        if voltage is None:
            return False

        sample_time = self._parse_sample_time(device_data.get("last_contact"))
        last_contact = device_data.get("last_contact")
        sample_id = f"{last_contact}:{voltage}" if last_contact is not None else ""
        return self.process_voltage(
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
    ) -> bool:
        """Record a voltage sample and update charge diagnostics."""
        state = self.state_for(mac)
        if sample_id is not None and state._last_sample_id == sample_id:
            return False

        state._last_sample_id = sample_id
        current_day = dt_util.as_local(now).date()
        if voltage > BATTERY_CHARGE_MAX_STAT_VOLTAGE:
            state._excluded_samples_by_day[current_day] += 1
        else:
            state._samples_by_day[current_day].append(voltage)
            state.voltage_max = self._max_voltage(state.voltage_max, voltage)
            state.voltage_min = self._min_voltage(state.voltage_min, voltage)
        self._prune_history(state, current_day)
        self._update_state(state, current_day, now)
        return True

    def as_storage_data(self) -> dict[str, Any]:
        """Return serializable battery tracker state."""
        panels: dict[str, Any] = {}

        for mac, state in self._states.items():
            panels[mac] = {
                "last_charged": state.last_charged.isoformat()
                if state.last_charged
                else None,
                "voltage_max": state.voltage_max,
                "voltage_min": state.voltage_min,
                "samples_by_day": {
                    sample_day.isoformat(): samples
                    for sample_day, samples in state._samples_by_day.items()
                },
                "excluded_samples_by_day": {
                    sample_day.isoformat(): count
                    for sample_day, count in state._excluded_samples_by_day.items()
                },
                "last_sample_id": state._last_sample_id,
                "last_detected_day": state._last_detected_day.isoformat()
                if state._last_detected_day
                else None,
            }

        return {"panels": panels}

    def load_storage_data(self, data: dict[str, Any] | None) -> None:
        """Load battery tracker state from storage."""
        if not isinstance(data, dict):
            return

        panels = data.get("panels")
        if not isinstance(panels, dict):
            return

        for mac, panel_data in panels.items():
            if not isinstance(panel_data, dict):
                continue

            state = self.state_for(str(mac))
            state.last_charged = self._parse_sample_time(panel_data.get("last_charged"))
            state.voltage_max = self._parse_voltage(panel_data.get("voltage_max"))
            state.voltage_min = self._parse_voltage(panel_data.get("voltage_min"))
            state._samples_by_day = self._restore_samples_by_day(
                panel_data.get("samples_by_day")
            )
            state._excluded_samples_by_day = self._restore_excluded_samples_by_day(
                panel_data.get("excluded_samples_by_day")
            )
            state._last_sample_id = panel_data.get("last_sample_id")
            state._last_detected_day = self._parse_day(
                panel_data.get("last_detected_day")
            )

            latest_day = self._latest_sample_day(state)
            if latest_day is not None:
                self._prune_history(state, latest_day)
                self._update_state(state, latest_day, dt_util.now())

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
        """Recalculate daily averages and charge status."""
        current_samples = state._samples_by_day.get(current_day, [])
        state.daily_samples = len(current_samples)
        state.excluded_daily_samples = state._excluded_samples_by_day[current_day]
        state.daily_average = self._daily_average(current_samples)
        previous_averages = self._previous_averages(state, current_day)
        state.previous_average = (
            round(sum(previous_averages) / len(previous_averages), 2)
            if len(previous_averages) == BATTERY_CHARGE_BASELINE_DAYS
            else None
        )
        state.stored_days = self._stored_days(state)
        state.valid_baseline_days = min(
            len(previous_averages),
            BATTERY_CHARGE_BASELINE_DAYS,
        )

        if state.daily_average is None:
            state.status = "insufficient_samples"
            return

        if state.previous_average is None:
            state.status = "baseline"
            return

        if self._in_cooldown(state, current_day):
            state.status = "cooldown"
            return

        increase = state.daily_average - state.previous_average
        if increase >= BATTERY_CHARGE_THRESHOLD_VOLTS:
            state.last_charged = now
            state._last_detected_day = current_day
            state.status = "charge_detected"
            return

        state.status = "idle"

    def _previous_averages(
        self,
        state: BatteryChargeState,
        current_day: date,
    ) -> list[float]:
        """Return daily averages from previous valid baseline days."""
        daily_averages: list[float] = []
        previous_days = [
            sample_day
            for sample_day in sorted(state._samples_by_day, reverse=True)
            if sample_day < current_day
        ]

        for sample_day in previous_days:
            daily_average = self._daily_average(state._samples_by_day[sample_day])
            if daily_average is None:
                continue

            daily_averages.append(daily_average)
            if len(daily_averages) == BATTERY_CHARGE_BASELINE_DAYS:
                return daily_averages

        return daily_averages

    def _daily_average(self, samples: list[float]) -> float | None:
        """Return the average battery voltage for a day."""
        if not samples:
            return None

        return round(sum(samples) / len(samples), 2)

    def _in_cooldown(self, state: BatteryChargeState, current_day: date) -> bool:
        """Return whether a recent charge detection is still in cooldown."""
        if state._last_detected_day is None:
            return False

        return (
            current_day - state._last_detected_day
        ).days < BATTERY_CHARGE_COOLDOWN_DAYS

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

    def _parse_voltage(self, value: Any) -> float | None:
        """Parse and round a battery voltage value."""
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _max_voltage(self, current: float | None, voltage: float) -> float:
        """Return updated maximum voltage."""
        if current is None:
            return voltage
        return max(current, voltage)

    def _min_voltage(self, current: float | None, voltage: float) -> float:
        """Return updated minimum voltage."""
        if current is None:
            return voltage
        return min(current, voltage)

    def _restore_samples_by_day(self, value: Any) -> dict[date, list[float]]:
        """Restore daily battery samples from storage."""
        samples_by_day: dict[date, list[float]] = defaultdict(list)
        if not isinstance(value, dict):
            return samples_by_day

        for raw_day, raw_samples in value.items():
            sample_day = self._parse_day(raw_day)
            if sample_day is None or not isinstance(raw_samples, list):
                continue

            samples = [
                parsed
                for raw_sample in raw_samples
                if (parsed := self._parse_voltage(raw_sample)) is not None
            ]
            if samples:
                samples_by_day[sample_day] = samples

        return samples_by_day

    def _restore_excluded_samples_by_day(self, value: Any) -> dict[date, int]:
        """Restore excluded daily sample counts from storage."""
        excluded_samples_by_day: dict[date, int] = defaultdict(int)
        if not isinstance(value, dict):
            return excluded_samples_by_day

        for raw_day, raw_count in value.items():
            sample_day = self._parse_day(raw_day)
            if sample_day is None:
                continue

            try:
                excluded_samples_by_day[sample_day] = int(raw_count)
            except (TypeError, ValueError):
                continue

        return excluded_samples_by_day

    def _parse_day(self, value: Any) -> date | None:
        """Parse a stored date key."""
        if value is None:
            return None

        if isinstance(value, date) and not isinstance(value, datetime):
            return value

        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def _latest_sample_day(self, state: BatteryChargeState) -> date | None:
        """Return the latest known battery sample day."""
        sample_days = set(state._samples_by_day) | set(state._excluded_samples_by_day)
        if not sample_days:
            return None

        return max(sample_days)

    def _stored_days(self, state: BatteryChargeState) -> int:
        """Return number of stored days with valid voltage samples."""
        return sum(
            1
            for samples in state._samples_by_day.values()
            if self._daily_average(samples) is not None
        )
