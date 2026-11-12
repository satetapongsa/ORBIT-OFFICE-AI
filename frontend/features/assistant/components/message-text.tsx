import Link from "next/link";
import type { ReactNode } from "react";

// Only standalone in-app paths with a UUID become links (not parts of other URLs).
const IN_APP_LINK =
  /(?<![\w.:/-])(\/(?:tasks|documents|employees|helpdesk)\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/gi;

/**
 * Model output is untrusted: it is rendered as plain text (never HTML or Markdown), with
 * in-app links to tasks, documents, people and IT tickets made clickable.
 */
export function MessageText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(IN_APP_LINK)) {
    const start = match.index ?? 0;
    if (start > last) parts.push(text.slice(last, start));
    parts.push(
      <Link key={start} href={match[0]} className="text-primary underline underline-offset-2">
        {match[0]}
      </Link>,
    );
    last = start + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <p className="text-sm leading-relaxed break-words whitespace-pre-wrap">{parts}</p>;
}
