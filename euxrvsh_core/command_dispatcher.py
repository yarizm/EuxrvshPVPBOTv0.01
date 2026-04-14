from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DispatchResult:
    matched: bool
    action: str = ""
    args: list[str] = field(default_factory=list)


class PvpCommandDispatcher:
    def dispatch(self, raw_message: str) -> DispatchResult:
        if not raw_message:
            return DispatchResult(matched=False)

        message = raw_message.strip()
        if not message:
            return DispatchResult(matched=False)

        parts = message.split()
        if not parts or parts[0].lower() != "/pvp":
            return DispatchResult(matched=False)
        if len(parts) == 1:
            return DispatchResult(matched=True, action="help", args=[])

        return DispatchResult(matched=True, action=parts[1].lower(), args=parts[2:])
