from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.util import dt as dt_util


@dataclass
class DisplayActivityState:
    """Daily contact and display refresh diagnostics for one panel."""

    day: date | None = None
    daily_contacts: int = 0
    daily_display_refreshes: int = 0
    last_counted_contact: str | None = None
    last_display_refresh_ms: float | None = None

    @property
    def refresh_ratio(self) -> float | None:
        """Return the display refresh ratio for counted daily contacts."""
        if self.daily_contacts <= 0:
            return None
        return round(self.daily_display_refreshes / self.daily_contacts, 3)

    @property
    def refresh_percentage(self) -> float | None:
        """Return the display refresh percentage for counted daily contacts."""
        if self.daily_contacts <= 0:
            return None
        return round((self.daily_display_refreshes / self.daily_contacts) * 100, 1)


class DisplayActivityTracker:
    """Track observed panel contacts and display refreshes per local day."""

    def __init__(self) -> None:
        """Initialize the tracker."""
        self._states: dict[str, DisplayActivityState] = {}

    def state_for(self, mac: str) -> DisplayActivityState:
        """Return activity state for a panel."""
        return self._states.setdefault(mac, DisplayActivityState())

    def process_device(self, mac: str, device_data: dict[str, Any]) -> bool:
        """Process one panel payload and update daily activity counters."""
        last_contact = device_data.get("last_contact")
        if not last_contact:
            return False

        state = self.state_for(mac)
        changed = self._ensure_today(state)
        contact_id = str(last_contact)

        if state.last_counted_contact == contact_id:
            return changed

        state.last_counted_contact = contact_id
        state.daily_contacts += 1
        state.last_display_refresh_ms = self._parse_refresh_ms(
            device_data.get("last_display_refresh_ms")
        )

        if state.last_display_refresh_ms is not None:
            state.daily_display_refreshes += 1

        return True

    def reset_for_new_day(self) -> bool:
        """Reset all daily counters when Home Assistant reaches a new local day."""
        changed = False

        for state in self._states.values():
            if self._ensure_today(state):
                changed = True

        return changed

    def as_storage_data(self) -> dict[str, Any]:
        """Return serializable display activity tracker state."""
        panels: dict[str, Any] = {}

        for mac, state in self._states.items():
            panels[mac] = {
                "day": state.day.isoformat() if state.day else None,
                "daily_contacts": state.daily_contacts,
                "daily_display_refreshes": state.daily_display_refreshes,
                "last_counted_contact": state.last_counted_contact,
                "last_display_refresh_ms": state.last_display_refresh_ms,
            }

        return {"panels": panels}

    def load_storage_data(self, data: dict[str, Any] | None) -> None:
        """Load display activity tracker state from storage."""
        if not isinstance(data, dict):
            return

        panels = data.get("panels")
        if not isinstance(panels, dict):
            return

        for mac, panel_data in panels.items():
            if not isinstance(panel_data, dict):
                continue

            state = self.state_for(str(mac))
            state.day = self._parse_day(panel_data.get("day"))
            state.daily_contacts = self._parse_count(
                panel_data.get("daily_contacts")
            )
            state.daily_display_refreshes = self._parse_count(
                panel_data.get("daily_display_refreshes")
            )
            last_counted_contact = panel_data.get("last_counted_contact")
            state.last_counted_contact = (
                str(last_counted_contact)
                if last_counted_contact is not None
                else None
            )
            state.last_display_refresh_ms = self._parse_refresh_ms(
                panel_data.get("last_display_refresh_ms")
            )
            self._ensure_today(state)

    def _ensure_today(self, state: DisplayActivityState) -> bool:
        """Reset daily counters when Home Assistant moves to a new local day."""
        today = dt_util.now().date()
        if state.day == today:
            return False

        state.day = today
        state.daily_contacts = 0
        state.daily_display_refreshes = 0
        state.last_display_refresh_ms = None
        return True

    def _parse_count(self, value: Any) -> int:
        """Parse a stored counter value."""
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def _parse_day(self, value: Any) -> date | None:
        """Parse a stored local day value."""
        if value is None:
            return None

        if isinstance(value, date):
            return value

        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def _parse_refresh_ms(self, value: Any) -> float | None:
        """Parse a display refresh duration from the panel payload."""
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None
