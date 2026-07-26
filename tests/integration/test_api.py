"""Integration: the API layer end to end, plus smoothing behavior."""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from waterfall.api.app import app
from waterfall.api.schemas import ParamsIn, RenderStateOut
from waterfall.api.stream import Session
from waterfall.domain.constants import DB_PER_OCTAVE_UNIT, EQ_BAND_COUNT
from waterfall.domain.spectrum import SpectrumParams
from waterfall.domain.state import render_state
from waterfall.engine.smoothing import ParameterSmoother

UNIT = DB_PER_OCTAVE_UNIT


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --- HTTP --------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_render_endpoint_returns_white_for_white_noise(client: TestClient) -> None:
    response = client.post("/render", json={})
    assert response.status_code == 200
    body = RenderStateOut.model_validate(response.json())
    assert body.water.color == pytest.approx((1.0, 1.0, 1.0), abs=1e-6)
    assert body.water.turbulence == pytest.approx(1.0)
    assert body.water.fall_speed == pytest.approx(0.5)


def test_render_endpoint_ships_the_full_filter_chain(client: TestClient) -> None:
    plain = RenderStateOut.model_validate(client.post("/render", json={}).json())
    with_band = RenderStateOut.model_validate(
        client.post("/render", json={"band_gain_db": 12.0}).json()
    )
    # Constant node count either way: the emphasis band is always shipped, at
    # 0 dB when off, so the browser never rebuilds its graph mid-playback.
    assert len(plain.audio.bands) == EQ_BAND_COUNT + 1
    assert len(with_band.audio.bands) == EQ_BAND_COUNT + 1
    assert plain.audio.bands[-1].gain_db == 0.0


@pytest.mark.parametrize(
    "payload",
    [{"level_db": 6.0}, {"slope_db_per_oct": 99.0}, {"band_center_hz": 1.0}],
)
def test_out_of_range_requests_are_rejected(
    client: TestClient, payload: dict[str, float]
) -> None:
    """Level above 0 dBFS is rejected at the edge: it would clip the audio."""
    assert client.post("/render", json=payload).status_code == 422


# --- WebSocket ---------------------------------------------------------------


def test_websocket_streams_render_states(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        state = RenderStateOut.model_validate(ws.receive_json())
        assert len(state.audio.bands) == EQ_BAND_COUNT + 1
        assert 0.0 <= state.water.turbulence <= 1.0


def test_websocket_eases_toward_a_new_target(client: TestClient) -> None:
    """A parameter change arrives gradually, not as a jump."""
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json(ParamsIn(slope_db_per_oct=-2 * UNIT).model_dump())

        reds = []
        for _ in range(40):
            reds.append(RenderStateOut.model_validate(ws.receive_json()).water.color[0])

        # Still white at the start, and moving toward red rather than snapping.
        assert reds[-1] >= reds[0]
        assert any(0.0 < r < 1.0 for r in reds), "expected intermediate frames"


def test_websocket_survives_a_malformed_update(client: TestClient) -> None:
    """A bad message must not kill the audio -- the listener keeps hearing the
    last good sound."""
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"slope_db_per_oct": "not a number"})
        assert RenderStateOut.model_validate(ws.receive_json()) is not None


# --- Smoothing ---------------------------------------------------------------


def test_smoother_converges_without_overshoot() -> None:
    target = SpectrumParams(slope_db_per_oct=-2 * UNIT, level_db=-24.0)
    smoother = ParameterSmoother(current=SpectrumParams())

    previous_slope = 0.0
    for _ in range(500):
        current = smoother.step(target)
        assert target.slope_db_per_oct <= current.slope_db_per_oct <= 0.0, "overshoot"
        assert current.slope_db_per_oct <= previous_slope, "not monotonic"
        previous_slope = current.slope_db_per_oct

    assert smoother.has_converged(target)


def test_smoother_eases_band_center_in_log_space() -> None:
    """One octave should take the same time at the bottom of the range as the top."""
    low = ParameterSmoother(current=SpectrumParams(band_center_hz=100.0))
    high = ParameterSmoother(current=SpectrumParams(band_center_hz=1000.0))

    low_step = low.step(SpectrumParams(band_center_hz=200.0))
    high_step = high.step(SpectrumParams(band_center_hz=2000.0))

    low_octaves = (low_step.band_center_hz / 100.0) ** 1
    high_octaves = (high_step.band_center_hz / 1000.0) ** 1
    assert low_octaves == pytest.approx(high_octaves, rel=1e-9)


def test_session_reaches_the_requested_state() -> None:
    session = Session()
    target = SpectrumParams(slope_db_per_oct=2 * UNIT, band_gain_db=12.0)
    session.set_target(target)

    for _ in range(1000):
        session.next_state()

    assert session.settled()
    settled = session.next_state()
    expected = render_state(target)
    assert settled.water.color == pytest.approx(expected.water.color, abs=1e-4)


def test_rejected_smoothing_rate() -> None:
    with pytest.raises(ValueError):
        ParameterSmoother(current=SpectrumParams(), rate=0.0)


def test_params_round_trip_through_the_wire_schema() -> None:
    original = SpectrumParams(
        slope_db_per_oct=-UNIT, band_gain_db=9.0, band_center_hz=440.0,
        band_width_oct=0.75, level_db=-9.0,
    )
    restored = ParamsIn.model_validate(dataclasses.asdict(original)).to_domain()
    assert restored == original
