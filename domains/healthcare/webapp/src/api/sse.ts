// Pure, incremental SSE parser. No I/O — feed it decoded text chunks.

export interface SseEvent {
  id?: string;
  event?: string;
  data: string;
}

export interface SseParser {
  /** Push a decoded chunk; returns the events completed by this chunk. */
  push(chunk: string): SseEvent[];
  /** Flush any trailing event when the stream ends. */
  end(): SseEvent[];
}

export function createSseParser(): SseParser {
  let buffer = "";
  let dataLines: string[] = [];
  let id: string | undefined;
  let eventName: string | undefined;

  function dispatch(out: SseEvent[]): void {
    if (dataLines.length) {
      const evt: SseEvent = { data: dataLines.join("\n") };
      if (id !== undefined) evt.id = id;
      if (eventName !== undefined) evt.event = eventName;
      out.push(evt);
    }
    dataLines = [];
    eventName = undefined;
    // Scope ids to the event that declared them so dedupe never drops id-less events.
    id = undefined;
  }

  function processLine(line: string, out: SseEvent[]): void {
    if (line === "") {
      dispatch(out);
      return;
    }
    if (line.startsWith(":")) return;
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    let value = idx === -1 ? "" : line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") dataLines.push(value);
    else if (field === "id") id = value;
    else if (field === "event") eventName = value;
  }

  return {
    push(chunk) {
      const out: SseEvent[] = [];
      buffer += chunk;
      // A trailing CR may be the first half of a CRLF split across chunks.
      const heldCr = buffer.endsWith("\r");
      const lines = (heldCr ? buffer.slice(0, -1) : buffer).split(/\r\n|\r|\n/);
      // Retain the trailing partial line for the next chunk.
      buffer = (lines.pop() ?? "") + (heldCr ? "\r" : "");
      for (const line of lines) processLine(line, out);
      return out;
    },
    end() {
      const out: SseEvent[] = [];
      if (buffer) processLine(buffer.replace(/\r$/, ""), out);
      buffer = "";
      dispatch(out);
      return out;
    },
  };
}

/** Parse an SSE event's data as JSON, returning undefined for malformed frames. */
export function parseEventJson(evt: SseEvent): unknown {
  try {
    return JSON.parse(evt.data) as unknown;
  } catch {
    return undefined;
  }
}
