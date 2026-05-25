const API_BASE = '/api';

export interface SSEEvent {
  type: string;
  data: Record<string, string>;
}

type SSECallbacks = {
  onEvent: (event: SSEEvent) => void;
  onError: (error: Error) => void;
  onDone: () => void;
};

function parseSSEStream(
  response: Response,
  { onEvent, onError, onDone }: SSECallbacks,
) {
  const reader = response.body?.getReader();
  if (!reader) {
    onError(new Error('No response body'));
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  (async () => {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      let currentEvent = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          const data = line.slice(6);
          try {
            onEvent({ type: currentEvent, data: JSON.parse(data) });
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
    onDone();
  })().catch((err) => {
    if (err.name !== 'AbortError') {
      onError(err);
    }
  });
}

export function streamGenerate(
  message: string,
  onEvent: (event: SSEEvent) => void,
  onError: (error: Error) => void,
  onDone: () => void,
): AbortController {
  const controller = new AbortController();

  fetch(`${API_BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal: controller.signal,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      parseSSEStream(response, { onEvent, onError, onDone });
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err);
      }
    });

  return controller;
}

export function streamResume(
  threadId: string,
  answers: string,
  onEvent: (event: SSEEvent) => void,
  onError: (error: Error) => void,
  onDone: () => void,
): AbortController {
  const controller = new AbortController();

  fetch(`${API_BASE}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, answers }),
    signal: controller.signal,
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      parseSSEStream(response, { onEvent, onError, onDone });
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err);
      }
    });

  return controller;
}

export async function fetchTickets(): Promise<{ id: string; message: string; status: string; created_at: string }[]> {
  const res = await fetch(`${API_BASE}/tickets`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.items;
}

export async function fetchTicketDetail(ticketId: string): Promise<{
  id: string;
  message: string;
  status: string;
  created_at: string;
  report: { research_brief?: string; draft_report?: string; final_report?: string };
}> {
  const res = await fetch(`${API_BASE}/tickets/${ticketId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
