from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    assets_dir: Path
    output_dir: Path
    turbine_coordinates: tuple[tuple[float, float], ...] = (
        (43.645150, 78.535604),
        (43.643198, 78.538828),
    )
    horizon_hours: int = 48
    ridge_alpha: float = 0.5

    @property
    def turbine_files(self) -> list[Path]:
        return sorted(self.assets_dir.glob("*turbine*.csv"))


def default_settings(project_root: Path | None = None) -> Settings:
    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    return Settings(
        project_root=root,
        assets_dir=root / "assets",
        output_dir=root / "outputs",
    )
