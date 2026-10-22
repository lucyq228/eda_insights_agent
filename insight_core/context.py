from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class Ctx:
    """What every tool receives: the data, the scope, and where to write."""

    run_dir: Path
    df: pd.DataFrame
    types: dict[str, str]
    scope: dict
    label: str
    drivers: list[str] = field(default_factory=list)

    @property
    def target(self) -> str:
        return self.scope["target"]["column"]

    @property
    def target_type(self) -> str:
        return self.scope["target"]["type"]

    @property
    def entity(self) -> str | None:
        return self.scope.get("entity_column")

    @property
    def min_n(self) -> int:
        return int(self.scope.get("min_n", 30))

    @property
    def alpha(self) -> float:
        return float(self.scope.get("alpha", .05))

    def chart(self, name: str) -> Path:
        return self.run_dir / "charts" / f"{self.label}__{name}.png"
