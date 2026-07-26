/**
 * Transport to the Python engine.
 *
 * The browser never computes a color or designs a filter; it asks for a
 * RenderState and applies it. Keeping every number on one side is what stops
 * the color and the sound from drifting apart.
 */

import type { AudioParams } from "./audio";
import type { WaterState } from "./scene";
import type { Params } from "./controls";

export interface RenderState {
  water: WaterState;
  audio: AudioParams;
}

const RECONNECT_MS = 1000;

export class EngineSocket {
  private socket: WebSocket | null = null;
  private pending: Params | null = null;
  private closed = false;
  private onState: (state: RenderState) => void = () => {};

  constructor(private readonly url: string) {}

  subscribe(handler: (state: RenderState) => void): void {
    this.onState = handler;
  }

  connect(): void {
    if (this.closed) return;
    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.addEventListener("open", () => {
      if (this.pending) this.send(this.pending);
    });
    socket.addEventListener("message", (event) => {
      this.onState(JSON.parse(event.data as string) as RenderState);
    });
    socket.addEventListener("close", () => {
      // Retry rather than fail silently: a dropped socket would otherwise
      // freeze the water mid-fall with no indication why.
      if (!this.closed) window.setTimeout(() => this.connect(), RECONNECT_MS);
    });
  }

  send(params: Params): void {
    this.pending = params;
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(params));
    }
  }

  close(): void {
    this.closed = true;
    this.socket?.close();
  }
}

/** One-shot render, used by the deterministic test mode where a live stream
 * would make frames depend on wall-clock timing. */
export async function renderOnce(params: Params): Promise<RenderState> {
  const response = await fetch("/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(`render failed: ${response.status}`);
  return (await response.json()) as RenderState;
}
