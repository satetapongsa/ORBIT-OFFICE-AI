"use client";

import { Loader2, Search, UserPlus, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAssignableUsers } from "@/features/tasks/hooks/use-tasks";

export interface PickedUser {
  id: string;
  display_name: string;
}

interface AssigneePickerProps {
  value: PickedUser[];
  onChange: (value: PickedUser[]) => void;
  disabled?: boolean;
  max?: number;
}

function useDebounced(value: string, delay = 250): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Search people the current user may assign (the backend decides who that is). */
export function AssigneePicker({ value, onChange, disabled, max = 20 }: AssigneePickerProps) {
  const id = useId();
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const results = useAssignableUsers(q, !disabled);
  const chosen = new Set(value.map((u) => u.id));
  const options = (results.data ?? []).filter((u) => !chosen.has(u.id));

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>ผู้รับผิดชอบ</Label>
      {value.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="ผู้รับผิดชอบที่เลือก">
          {value.map((u) => (
            <li
              key={u.id}
              className="bg-secondary inline-flex items-center gap-1 rounded-full py-0.5 pr-1 pl-2.5 text-xs"
            >
              {u.display_name}
              <button
                type="button"
                className="hover:bg-background/80 rounded-full p-0.5"
                aria-label={`นำ ${u.display_name} ออก`}
                disabled={disabled}
                onClick={() => onChange(value.filter((v) => v.id !== u.id))}
              >
                <X className="size-3" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-xs">
          ยังไม่ได้เลือก — ถ้าไม่เลือก งานจะมอบหมายให้คุณเอง
        </p>
      )}
      <div className="relative">
        <Search
          className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          aria-hidden
        />
        <Input
          id={id}
          type="search"
          className="pl-8"
          placeholder="ค้นหาชื่อหรือตำแหน่ง"
          value={search}
          maxLength={100}
          disabled={disabled || value.length >= max}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <div className="max-h-44 overflow-y-auto rounded-md border" aria-live="polite">
        {results.isPending ? (
          <div className="text-muted-foreground flex items-center gap-2 p-3 text-xs">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            กำลังค้นหา…
          </div>
        ) : options.length === 0 ? (
          <p className="text-muted-foreground p-3 text-xs">ไม่พบผู้ที่คุณมอบหมายงานได้</p>
        ) : (
          <ul aria-label="ผลการค้นหาผู้รับผิดชอบ">
            {options.map((u) => (
              <li key={u.id} className="flex items-center justify-between gap-2 px-3 py-1.5">
                <span className="min-w-0 text-sm">
                  <span className="block truncate">{u.display_name}</span>
                  <span className="text-muted-foreground block truncate text-xs">
                    {[u.job_title, u.department?.name].filter(Boolean).join(" · ") || "—"}
                  </span>
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={disabled || value.length >= max}
                  aria-label={`เพิ่ม ${u.display_name}`}
                  onClick={() => {
                    onChange([...value, { id: u.id, display_name: u.display_name }]);
                    setSearch("");
                  }}
                >
                  <UserPlus aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
