"""Invariant 3: every control changes both the sound and the color.

This is the app's defining rule, mechanized. The purpose of the app is to pick a
sound you like and see what color it is -- so a control that repaints the water
without altering what you hear is a lie, and a control that alters the sound
without moving the color is invisible. Either one breaks the premise.

This test is what would have caught the wavelength-mapping toggle that an
earlier design carried: it changed the color and nothing else.
"""

from __future__ import annotations

import dataclasses

import pytest

from tests.unit.test_colorimetry import delta_e
from waterfall.domain.colorimetry import to_hex
from waterfall.domain.state import RenderState, render_state
from waterfall.domain.spectrum import SpectrumParams

# Band gain is non-zero so that band center and width are live. With the band
# disabled they are legitimately inert -- see the dedicated test below.
BASELINE = SpectrumParams(
    slope_db_per_oct=0.0,
    band_gain_db=6.0,
    band_center_hz=1000.0,
    band_width_oct=1.0,
    level_db=-6.0,
)

PERTURBATIONS = {
    "slope_db_per_oct": -4.0,
    "band_gain_db": 12.0,
    "band_center_hz": 4000.0,
    "band_width_oct": 0.2,
    "level_db": -18.0,
}


def audio_signature(state: RenderState) -> tuple[object, ...]:
    """Everything that determines what the listener actually hears."""
    return (
        tuple((b.frequency_hz, b.gain_db, b.q) for b in state.audio.bands),
        state.audio.output_gain,
    )


@pytest.mark.parametrize("control", sorted(PERTURBATIONS))
def test_control_changes_both_sound_and_color(control: str) -> None:
    before = render_state(BASELINE)
    after = render_state(
        dataclasses.replace(BASELINE, **{control: PERTURBATIONS[control]})
    )

    assert audio_signature(before) != audio_signature(after), (
        f"{control} does not change the sound -- it would be a decorative control"
    )

    shifted = delta_e(to_hex(before.water.color), to_hex(after.water.color))
    assert shifted > 1.0, (
        f"{control} does not change the color (deltaE {shifted:.3f}) -- "
        "it would be an inaudible-to-the-eye control"
    )


@pytest.mark.parametrize("control", sorted(PERTURBATIONS))
def test_control_moves_the_water_state(control: str) -> None:
    """Sanity companion: the renderer payload actually differs too."""
    before = render_state(BASELINE).water
    after = render_state(
        dataclasses.replace(BASELINE, **{control: PERTURBATIONS[control]})
    ).water
    assert before != after


def test_band_parameters_are_inert_only_when_the_band_is_off() -> None:
    """The one documented exception, pinned so it stays intentional.

    With band gain at 0 dB there is no band, so its center and width have
    nothing to act on -- exactly like a disabled control. The UI must grey them
    out in this state; otherwise they look broken rather than inactive.
    """
    silent_band = SpectrumParams(band_gain_db=0.0, band_center_hz=1000.0)
    moved_center = dataclasses.replace(silent_band, band_center_hz=8000.0)
    moved_width = dataclasses.replace(silent_band, band_width_oct=2.0)

    # Neither the color nor the audible response moves. The emphasis node's
    # frequency does differ in the payload, but a peaking filter at 0 dB is
    # identity at any frequency or Q, so nothing reaches the listener's ears --
    # which is why this is asserted on the rendered result and the band's gain
    # rather than on payload equality.
    for variant in (moved_center, moved_width):
        assert render_state(silent_band).water == render_state(variant).water
        assert render_state(variant).audio.bands[-1].gain_db == 0.0

    # ... and the moment the band is switched on, both become live again.
    live = dataclasses.replace(silent_band, band_gain_db=12.0)
    assert render_state(live) != render_state(
        dataclasses.replace(live, band_center_hz=8000.0)
    )
