"""Generates the fixture that pins the browser's audio against Python's S(f).

This is one half of invariant 6. Python states, here, exactly what magnitude
response each parameter set should produce; tests/ui/audio-contract.spec.ts
measures what the browser actually produces and compares.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from waterfall.domain.filters import filter_chain, output_gain
from waterfall.domain.constants import (
    DB_PER_OCTAVE_UNIT,
    DECIBEL_BASE,
    FIT_HIGH_HZ,
    FIT_LOW_HZ,
    FREQ_REF_HZ,
    SOURCE_NOISE_RMS,
)
from waterfall.domain.spectrum import SpectrumParams, power_spectrum

FIXTURE_PATH = Path(__file__).with_name("audio_contract.json")

# The band the shelf gains are fitted over. Outside it the cascade is not asked
# to track anything, so the contract does not claim it does.
CHECK_LOW_HZ = FIT_LOW_HZ
CHECK_HIGH_HZ = FIT_HIGH_HZ
CHECK_POINTS = 48

CASES: dict[str, SpectrumParams] = {
    "white noise": SpectrumParams(),
    "pink": SpectrumParams(slope_db_per_oct=-DB_PER_OCTAVE_UNIT),
    "brown": SpectrumParams(slope_db_per_oct=-2 * DB_PER_OCTAVE_UNIT),
    "azure": SpectrumParams(slope_db_per_oct=DB_PER_OCTAVE_UNIT),
    "violet": SpectrumParams(slope_db_per_oct=2 * DB_PER_OCTAVE_UNIT),
    "band at 1 kHz": SpectrumParams(band_gain_db=12.0, band_center_hz=1000.0,
                                    band_width_oct=1.0),
    "narrow band": SpectrumParams(band_gain_db=12.0, band_center_hz=2000.0,
                                  band_width_oct=0.2),
    "tilted with band": SpectrumParams(slope_db_per_oct=-DB_PER_OCTAVE_UNIT,
                                       band_gain_db=9.0, band_center_hz=250.0,
                                       band_width_oct=1.0, level_db=-6.0),
}


def check_frequencies() -> np.ndarray:
    return np.logspace(
        np.log2(CHECK_LOW_HZ), np.log2(CHECK_HIGH_HZ), CHECK_POINTS, base=2.0
    )


def build() -> dict[str, Any]:
    frequencies = check_frequencies()
    cases = []
    for name, params in CASES.items():
        spectrum = power_spectrum(params, frequencies)
        reference = float(power_spectrum(params, np.array([FREQ_REF_HZ]))[0])
        # Power dB relative to the reference frequency. Relative, because the
        # overall level is carried by output_gain rather than by the filters.
        relative_db = DECIBEL_BASE * np.log10(spectrum / reference)
        cases.append(
            {
                "name": name,
                "bands": [
                    {
                        "kind": b.kind,
                        "frequency_hz": b.frequency_hz,
                        "gain_db": b.gain_db,
                        "q": b.q,
                    }
                    for b in filter_chain(params)
                ],
                "output_gain": output_gain(params),
                "expected": [
                    {"hz": float(f), "db": float(d)}
                    for f, d in zip(frequencies, relative_db, strict=True)
                ],
            }
        )
    return {
        "reference_hz": FREQ_REF_HZ,
        # Python sizes the output gain against this; the browser has to produce
        # it. If the noise generator ever changes shape, every level is wrong.
        "source_noise_rms": SOURCE_NOISE_RMS,
        "cases": cases,
    }


def write() -> None:
    FIXTURE_PATH.write_text(json.dumps(build(), indent=2) + "\n")


if __name__ == "__main__":
    write()
    print(f"wrote {FIXTURE_PATH}")
