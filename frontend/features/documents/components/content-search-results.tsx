"use client";

import { FileSearch, Sparkles } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useContentSearch } from "@/features/documents/hooks/use-documents";
import { CATEGORY_LABELS } from "@/features/documents/labels";
import { ApiError } from "@/services/api-client";

/** Passages that match a question, only from documents the user may read. */
export function ContentSearchResults({ query }: { query: string }) {
  const search = useContentSearch(query);

  if (!query) {
    return (
      <EmptyState
        icon={Sparkles}
        title="ค้นหาในเนื้อหาเอกสาร"
        description="พิมพ์คำถามหรือคำค้น เช่น “ลาพักร้อนได้กี่วัน” ระบบค้นจากข้อความในเอกสารที่คุณมีสิทธิ์เท่านั้น"
      />
    );
  }
  if (search.isPending) {
    return (
      <Card>
        <CardContent className="space-y-3" aria-busy="true" aria-label="กำลังค้นหาในเนื้อหา">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }
  if (search.isError) {
    return (
      <ErrorState
        message={search.error.message}
        requestId={search.error instanceof ApiError ? search.error.requestId : null}
        onRetry={() => void search.refetch()}
        retrying={search.isFetching}
      />
    );
  }
  const { results, mode, degraded } = search.data;
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs" data-testid="search-mode">
        {mode === "hybrid" ? "ค้นหาตามความหมายและคำ" : "ค้นหาตามคำ"}
        {degraded ? " (บริการค้นหาตามความหมายไม่พร้อมใช้งานชั่วคราว)" : ""}
      </p>
      {results.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title="ไม่พบเนื้อหาที่ตรงกับคำค้นในเอกสารที่คุณเข้าถึงได้"
          description="ลองใช้คำอื่น หรือเอกสารที่เกี่ยวข้องอาจยังไม่ได้แชร์ให้คุณ"
        />
      ) : (
        <ul className="space-y-3" aria-label="ผลการค้นหาในเนื้อหา">
          {results.map((r) => (
            <li key={r.document_id} data-testid="content-hit">
              <Card className="py-4">
                <CardContent className="space-y-2 px-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/documents/${r.document_id}`}
                      className="font-medium hover:underline"
                    >
                      {r.title}
                    </Link>
                    <Badge variant="secondary">{CATEGORY_LABELS[r.category]}</Badge>
                    {r.page ? (
                      <span className="text-muted-foreground text-xs">หน้า {r.page}</span>
                    ) : null}
                  </div>
                  {/* Document text is untrusted: plain text only. */}
                  <p className="text-muted-foreground line-clamp-3 text-sm whitespace-pre-line">
                    {r.snippet}
                  </p>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
