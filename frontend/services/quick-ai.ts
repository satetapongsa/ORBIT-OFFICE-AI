import { z } from "zod";

import { apiStream } from "@/services/api-client";

/** Mirrors backend `app/services/ai/quick.py` (ADR-066). */
export const QUICK_QUESTION_MAX_CHARS = 2000;

const quickEventSchema = z.discriminatedUnion("event", [
  z.object({ event: z.literal("delta"), data: z.object({ text: z.string() }) }),
  z.object({ event: z.literal("done"), data: z.object({}).passthrough() }),
  z.object({
    event: z.literal("error"),
    data: z.object({ code: z.string(), message: z.string() }),
  }),
]);

export type QuickEvent = z.infer<typeof quickEventSchema>;

function parseBlock(block: string): QuickEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  try {
    const parsed = quickEventSchema.safeParse({ event, data: JSON.parse(data.join("\n")) });
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

/** Ask one question; `onEvent` receives the answer as it streams. Nothing is stored. */
export async function streamQuickAnswer(
  question: string,
  onEvent: (event: QuickEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await apiStream("/ai/quick", { question }, signal);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const event = parseBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (event) onEvent(event);
      boundary = buffer.indexOf("\n\n");
    }
  }
  const tail = parseBlock(buffer);
  if (tail) onEvent(tail);
}

/**
 * Plain paragraphs from the model's text: the prompt asks for no Markdown, and stray markers
 * (#, **, __, `) are removed in case a model adds them anyway.
 */
export function toParagraphs(text: string): string[] {
  const clean = text
    .replace(/```[a-z]*\n?/gi, "")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/^#{1,6}[ \t]+/gm, "")
    .replace(/^[ \t]*[*-][ \t]+/gm, "• "); // spaces only: \s would eat blank lines
  return clean
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}
