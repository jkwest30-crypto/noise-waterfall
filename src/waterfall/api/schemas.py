"""Wire contracts. The browser sees nothing but these shapes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from waterfall.domain.constants import (
    BAND_GAIN_MAX_DB,
    BAND_GAIN_MIN_DB,
    BAND_WIDTH_DEFAULT_OCT,
    BAND_WIDTH_MAX_OCT,
    BAND_WIDTH_MIN_OCT,
    FREQ_MAX_HZ,
    FREQ_MIN_HZ,
    FREQ_REF_HZ,
    LEVEL_MAX_DB,
    LEVEL_MIN_DB,
    SLOPE_MAX_DB_PER_OCT,
    SLOPE_MIN_DB_PER_OCT,
)
from waterfall.domain.spectrum import SpectrumParams
from waterfall.domain.state import RenderState


class ParamsIn(BaseModel):
    """The five controls. Bounds mirror domain/constants.py exactly."""

    slope_db_per_oct: float = Field(
        default=0.0, ge=SLOPE_MIN_DB_PER_OCT, le=SLOPE_MAX_DB_PER_OCT
    )
    band_gain_db: float = Field(
        default=0.0, ge=BAND_GAIN_MIN_DB, le=BAND_GAIN_MAX_DB
    )
    band_center_hz: float = Field(default=FREQ_REF_HZ, ge=FREQ_MIN_HZ, le=FREQ_MAX_HZ)
    band_width_oct: float = Field(
        default=BAND_WIDTH_DEFAULT_OCT, ge=BAND_WIDTH_MIN_OCT, le=BAND_WIDTH_MAX_OCT
    )
    level_db: float = Field(default=0.0, ge=LEVEL_MIN_DB, le=LEVEL_MAX_DB)

    def to_domain(self) -> SpectrumParams:
        return SpectrumParams(
            slope_db_per_oct=self.slope_db_per_oct,
            band_gain_db=self.band_gain_db,
            band_center_hz=self.band_center_hz,
            band_width_oct=self.band_width_oct,
            level_db=self.level_db,
        )


class BiquadOut(BaseModel):
    kind: str
    frequency_hz: float
    gain_db: float
    q: float


class WaterOut(BaseModel):
    color: tuple[float, float, float]
    color_name: str
    flow: float
    turbulence: float
    fall_speed: float


class AudioOut(BaseModel):
    bands: list[BiquadOut]
    output_gain: float


class RenderStateOut(BaseModel):
    """Everything the browser needs: one color, three motion scalars, and the
    filter graph. Color and audio are derived from the same S(f) upstream."""

    water: WaterOut
    audio: AudioOut

    @classmethod
    def from_domain(cls, state: RenderState) -> RenderStateOut:
        return cls(
            water=WaterOut(
                color=state.water.color,
                color_name=state.water.color_name,
                flow=state.water.flow,
                turbulence=state.water.turbulence,
                fall_speed=state.water.fall_speed,
            ),
            audio=AudioOut(
                bands=[
                    BiquadOut(
                        kind=b.kind,
                        frequency_hz=b.frequency_hz,
                        gain_db=b.gain_db,
                        q=b.q,
                    )
                    for b in state.audio.bands
                ],
                output_gain=state.audio.output_gain,
            ),
        )
