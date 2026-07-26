"""WebSocket session: receive target parameters, stream eased render states."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from waterfall.api.schemas import ParamsIn, RenderStateOut
from waterfall.domain.spectrum import SpectrumParams
from waterfall.domain.state import RenderState, render_state
from waterfall.engine.smoothing import ParameterSmoother

FRAME_RATE_HZ = 60.0
FRAME_INTERVAL_S = 1.0 / FRAME_RATE_HZ


class Session:
    """One listener's state. Deliberately free of any WebSocket knowledge so it
    can be tested without a transport."""

    def __init__(self, initial: SpectrumParams | None = None) -> None:
        start = initial or SpectrumParams()
        self.target = start
        self.smoother = ParameterSmoother(current=start)

    def set_target(self, params: SpectrumParams) -> None:
        self.target = params

    def next_state(self) -> RenderState:
        """Advance one frame toward the target and render it."""
        return render_state(self.smoother.step(self.target))

    def settled(self) -> bool:
        return self.smoother.has_converged(self.target)


async def run_session(websocket: WebSocket) -> None:
    """Receive parameter updates and push render states at the frame rate.

    Reading and writing run concurrently so a slider drag never blocks the
    stream: the client can send as fast as it likes while frames keep flowing at
    a steady cadence.
    """
    await websocket.accept()
    session = Session()
    closed = asyncio.Event()

    async def receive_targets() -> None:
        try:
            while True:
                payload = await websocket.receive_json()
                try:
                    session.set_target(ParamsIn.model_validate(payload).to_domain())
                except (ValidationError, ValueError):
                    # A malformed or out-of-range update is ignored rather than
                    # closing the socket: the listener keeps hearing the last
                    # good sound instead of the audio cutting out.
                    continue
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            # Whichever side notices the disconnect first stops the other, so
            # the frame loop cannot go on writing to a closed socket.
            closed.set()

    receiver = asyncio.create_task(receive_targets())
    try:
        while not closed.is_set():
            await websocket.send_json(
                RenderStateOut.from_domain(session.next_state()).model_dump()
            )
            await asyncio.sleep(FRAME_INTERVAL_S)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        receiver.cancel()
        with contextlib.suppress(
            asyncio.CancelledError, WebSocketDisconnect, RuntimeError
        ):
            await receiver
