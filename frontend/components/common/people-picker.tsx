"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { useState } from "react";

import { Input } from "@/components/ui/input";
import { searchDirectory } from "@/services/documents";

/** Search the employee directory and collect people as removable chips. */
export interface Picked {
  id: string;
  display_name: string;
}

export function PeoplePicker({
  picked,
  onChange,
  placeholder = "พิมพ์ชื่อเพื่อเพิ่มผู้เข้าร่วม",
  label = "ค้นหาผู้เข้าร่วม",
  exclude = [],
}: {
  picked: Picked[];
  onChange: (p: Picked[]) => void;
  placeholder?: string;
  label?: string;
  /** Ids never offered (e.g. people who are already members). */
  exclude?: string[];
}) {
  const [q, setQ] = useState("");
  const results = useQuery({
    queryKey: ["directory", "search", q],
    queryFn: ({ signal }) => searchDirectory(q, signal),
    enabled: q.trim().length > 0,
  });
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {picked.map((p) => (
          <span
            key={p.id}
            className="bg-muted inline-flex items-center gap-1 rounded-full py-0.5 pr-1 pl-2.5 text-xs"
          >
            {p.display_name}
            <button
              type="button"
              aria-label={`นำ ${p.display_name} ออก`}
              onClick={() => onChange(picked.filter((x) => x.id !== p.id))}
              className="hover:bg-background rounded-full p-0.5"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
        ))}
      </div>
      <div className="relative">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
          aria-hidden
        />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={placeholder}
          aria-label={label}
          className="pl-8"
        />
        {q.trim() && results.data ? (
          <ul className="bg-popover absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border shadow-lg">
            {results.data.filter(
              (u) => !picked.some((p) => p.id === u.id) && !exclude.includes(u.id),
            ).length === 0 ? (
              <li className="text-muted-foreground p-2 text-sm">ไม่พบรายชื่อ</li>
            ) : (
              results.data
                .filter((u) => !picked.some((p) => p.id === u.id) && !exclude.includes(u.id))
                .map((u) => (
                  <li key={u.id}>
                    <button
                      type="button"
                      className="hover:bg-accent w-full px-3 py-2 text-left text-sm"
                      onClick={() => {
                        onChange([...picked, { id: u.id, display_name: u.display_name }]);
                        setQ("");
                      }}
                    >
                      {u.display_name}
                      <span className="text-muted-foreground block text-xs">
                        {[u.job_title, u.department?.name].filter(Boolean).join(" · ") || "—"}
                      </span>
                    </button>
                  </li>
                ))
            )}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
