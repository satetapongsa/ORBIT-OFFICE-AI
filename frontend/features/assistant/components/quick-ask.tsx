"use client";

import { Check, Copy, Loader2, Send, Sparkles, Square, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/features/auth/hooks/use-session";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import { QUICK_QUESTION_MAX_CHARS, streamQuickAnswer, toParagraphs } from "@/services/quick-ai";

const SUGGESTIONS = [
  "อธิบาย AI แบบเข้าใจง่าย",
  "ช่วยเขียนข้อความขอลางานแบบสุภาพ",
  "เคล็ดลับนอนหลับให้สนิท",
  "15% ของ 2,400 คือเท่าไร",
];

type Status = "idle" | "streaming" | "done" | "error";

/**
 * Round "ถาม AI" button in the header (ADR-066). One question, one answer: asking again
 * replaces the previous answer, closing the panel forgets everything, and the server stores
 * nothing.
 */
export function QuickAsk() {
  const { has } = useSession();
  if (!has("ai:chat")) return null;
  return <QuickAskPanel />;
}

function QuickAskPanel() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [question, setQuestion] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const forget = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setDraft("");
    setQuestion(null);
    setAnswer("");
    setStatus("idle");
    setError(null);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    forget(); // nothing is kept once the panel closes
    buttonRef.current?.focus();
  }, [forget]);

  // Close on Escape or a click outside the panel.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panelRef.current?.contains(target) && !buttonRef.current?.contains(target)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    inputRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, close]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function ask(text: string) {
    const q = text.trim();
    if (!q) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setQuestion(q);
    setAnswer("");
    setError(null);
    setCopied(false);
    setDraft("");
    setStatus("streaming");
    try {
      await streamQuickAnswer(
        q,
        (event) => {
          if (controller.signal.aborted) return;
          if (event.event === "delta") setAnswer((current) => current + event.data.text);
          else if (event.event === "error") {
            setError(event.data.message);
            setStatus("error");
          }
        },
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setStatus((current) => (current === "streaming" ? "done" : current));
      }
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(
        caught instanceof ApiError ? caught.message : "ไม่ได้รับคำตอบจากผู้ช่วย AI กรุณาลองใหม่",
      );
      setStatus("error");
    }
  }

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setStatus("done");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void ask(draft);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(toParagraphs(answer).join("\n\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard not available */
    }
  }

  const paragraphs = toParagraphs(answer);
  const streaming = status === "streaming";

  return (
    <>
      <Button
        ref={buttonRef}
        type="button"
        size="icon"
        onClick={() => (open ? close() : setOpen(true))}
        aria-label="ถาม AI"
        aria-expanded={open}
        aria-controls="quick-ask-panel"
        title="ถาม AI ได้ทุกเรื่อง"
        className="size-9 rounded-full shadow-sm"
      >
        <Sparkles className="size-4" aria-hidden />
      </Button>

      {open ? (
        <div
          ref={panelRef}
          id="quick-ask-panel"
          role="dialog"
          aria-label="ถาม AI"
          className="bg-popover text-popover-foreground fixed top-[4.5rem] right-3 z-50 flex max-h-[min(38rem,calc(100dvh-6rem))] w-[min(26rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border shadow-xl"
        >
          <header className="flex items-start gap-3 border-b px-4 py-3">
            <span className="bg-primary text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-full">
              <Sparkles className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">ถาม AI</p>
              <p className="text-muted-foreground text-xs">
                ถามได้ทุกเรื่อง · ถามทีละข้อ ไม่บันทึกประวัติ
              </p>
            </div>
            <Button variant="ghost" size="icon" className="size-8" onClick={close} aria-label="ปิด">
              <X aria-hidden />
            </Button>
          </header>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
            {question === null ? (
              <div className="space-y-2">
                <p className="text-muted-foreground text-sm">ลองถาม เช่น</p>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => void ask(s)}
                      className="hover:bg-accent rounded-full border px-3 py-1.5 text-left text-xs transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <div className="flex justify-end">
                  <p className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl px-3.5 py-2 text-sm [overflow-wrap:anywhere] whitespace-pre-wrap">
                    {question}
                  </p>
                </div>
                {error ? (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : paragraphs.length === 0 && streaming ? (
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                    กำลังคิด…
                  </p>
                ) : (
                  <div
                    className="space-y-3 text-sm leading-relaxed [overflow-wrap:anywhere]"
                    data-testid="quick-answer"
                  >
                    {paragraphs.map((p, i) => (
                      <p key={i} className="whitespace-pre-wrap">
                        {p}
                        {streaming && i === paragraphs.length - 1 ? (
                          <span
                            aria-hidden
                            className="bg-foreground/60 ml-0.5 inline-block h-4 w-0.5 animate-pulse align-text-bottom"
                          />
                        ) : null}
                      </p>
                    ))}
                  </div>
                )}
                {status === "done" && paragraphs.length > 0 ? (
                  <div className="flex justify-end">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={copy}
                      className="text-muted-foreground h-7"
                    >
                      {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                      {copied ? "คัดลอกแล้ว" : "คัดลอก"}
                    </Button>
                  </div>
                ) : null}
              </>
            )}
          </div>

          <form
            className="flex items-end gap-2 border-t p-3"
            onSubmit={(event) => {
              event.preventDefault();
              void ask(draft);
            }}
          >
            <Textarea
              ref={inputRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onKeyDown}
              maxLength={QUICK_QUESTION_MAX_CHARS}
              rows={1}
              placeholder={question === null ? "พิมพ์คำถาม แล้วกด Enter" : "ถามคำถามใหม่…"}
              aria-label="คำถาม"
              className="max-h-32 min-h-10 resize-none"
            />
            {streaming ? (
              <Button
                type="button"
                size="icon"
                variant="outline"
                onClick={stop}
                aria-label="หยุดตอบ"
              >
                <Square className="size-3.5" aria-hidden />
              </Button>
            ) : (
              <Button
                type="submit"
                size="icon"
                disabled={!draft.trim()}
                aria-label="ส่งคำถาม"
                className={cn(!draft.trim() && "opacity-60")}
              >
                <Send aria-hidden />
              </Button>
            )}
          </form>
        </div>
      ) : null}
    </>
  );
}
