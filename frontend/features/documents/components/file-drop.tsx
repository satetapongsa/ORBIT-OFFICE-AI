"use client";

import { FileUp, X } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui/button";
import { ACCEPTED_FILES, checkFile, formatBytes } from "@/features/documents/labels";
import { cn } from "@/lib/utils";

interface FileDropProps {
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}

/** File picker with drag-and-drop and an immediate (advisory) type/size check. */
export function FileDrop({ file, onChange, disabled = false }: FileDropProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choose = (next: File | null) => {
    if (next) {
      const problem = checkFile(next);
      setError(problem);
      onChange(problem ? null : next);
    } else {
      setError(null);
      onChange(null);
    }
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    if (!disabled) choose(event.dataTransfer.files[0] ?? null);
  };

  return (
    <div className="space-y-1.5">
      {file ? (
        <div className="bg-muted/40 flex items-center gap-3 rounded-lg border p-3 text-sm">
          <FileUp className="text-primary size-5 shrink-0" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium" data-testid="chosen-file">
              {file.name}
            </p>
            <p className="text-muted-foreground text-xs">{formatBytes(file.size)}</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="เอาไฟล์ออก"
            disabled={disabled}
            onClick={() => {
              choose(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
          >
            <X aria-hidden />
          </Button>
        </div>
      ) : (
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "hover:bg-muted/40 flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center text-sm transition-colors",
            dragging && "border-primary bg-primary/5",
            disabled && "pointer-events-none opacity-60",
          )}
        >
          <FileUp className="text-muted-foreground size-8" aria-hidden />
          <span className="font-medium">ลากไฟล์มาวาง หรือคลิกเพื่อเลือกไฟล์</span>
          <span className="text-muted-foreground text-xs">
            PDF, DOCX, XLSX หรือ TXT ไม่เกิน 25 MB
          </span>
        </label>
      )}
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={ACCEPTED_FILES}
        className="sr-only"
        aria-label="เลือกไฟล์เอกสาร"
        disabled={disabled}
        onChange={(e) => choose(e.target.files?.[0] ?? null)}
      />
      {error ? (
        <p role="alert" className="text-destructive text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
