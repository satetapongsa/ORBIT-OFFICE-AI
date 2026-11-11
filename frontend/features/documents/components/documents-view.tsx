"use client";

import { ChevronLeft, ChevronRight, FileSearch, FileText, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { NativeSelect } from "@/components/common/native-select";
import { PageHeader } from "@/components/common/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import { ContentSearchResults } from "@/features/documents/components/content-search-results";
import { ProcessingBadge } from "@/features/documents/components/processing-badge";
import { UploadDialog } from "@/features/documents/components/upload-dialog";
import { useDocumentList } from "@/features/documents/hooks/use-documents";
import {
  CATEGORY_LABELS,
  STATUS_LABELS,
  VISIBILITY_LABELS,
  formatBytes,
} from "@/features/documents/labels";
import { formatDateTime, formatRelative } from "@/lib/format";
import { ApiError } from "@/services/api-client";
import {
  categorySchema,
  visibilitySchema,
  type DocumentCategory,
  type DocumentListItem,
  type DocumentListParams,
  type DocumentVisibility,
} from "@/services/documents";

const PAGE_SIZE = 20;

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function DocumentRow({ doc }: { doc: DocumentListItem }) {
  const version = doc.current_version;
  return (
    <li data-testid="document-row">
      <Link
        href={`/documents/${doc.id}`}
        className="hover:bg-muted/50 focus-visible:ring-ring/50 grid gap-2 rounded-lg px-3 py-3 outline-none focus-visible:ring-2 md:grid-cols-[minmax(0,1fr)_9rem_8rem_9rem] md:items-center md:gap-4"
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="bg-primary/10 text-primary mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg text-[10px] font-semibold">
            {version?.file_type ?? <FileText className="size-4" aria-hidden />}
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium">{doc.title}</p>
            <p className="text-muted-foreground truncate text-xs">
              {doc.owner.display_name}
              {doc.department ? ` · ${doc.department.name}` : ""}
              {version ? ` · ${formatBytes(version.size_bytes)}` : ""}
              {version && version.version_number > 1 ? ` · ฉบับที่ ${version.version_number}` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 md:block">
          <Badge variant="secondary">{CATEGORY_LABELS[doc.category]}</Badge>
          {doc.status !== "ACTIVE" ? (
            <Badge variant="outline" className="md:mt-1">
              {STATUS_LABELS[doc.status]}
            </Badge>
          ) : null}
        </div>
        <div className="text-muted-foreground text-xs md:text-sm">
          {VISIBILITY_LABELS[doc.visibility].label}
        </div>
        <div className="flex items-center justify-between gap-2 md:flex-col md:items-end">
          {version ? <ProcessingBadge status={version.processing_status} /> : null}
          <time
            dateTime={doc.updated_at}
            title={formatDateTime(doc.updated_at)}
            className="text-muted-foreground text-xs"
          >
            {formatRelative(doc.updated_at)}
          </time>
        </div>
      </Link>
    </li>
  );
}

export function DocumentsView() {
  const { has } = useSession();
  const ids = { q: useId(), category: useId(), visibility: useId(), sort: useId() };
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<DocumentCategory | "">("");
  const [visibility, setVisibility] = useState<DocumentVisibility | "">("");
  const [mine, setMine] = useState(false);
  const [inContent, setInContent] = useState(false);
  const [sort, setSort] = useState<NonNullable<DocumentListParams["sort"]>>("updated");
  const [page, setPage] = useState(1);
  const q = useDebounced(search.trim());

  const params: DocumentListParams = {
    q: q || undefined,
    category: category || undefined,
    visibility: visibility || undefined,
    mine,
    sort,
    page,
    pageSize: PAGE_SIZE,
  };
  const list = useDocumentList(params);
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;
  const filtered = Boolean(q || category || visibility || mine);
  const resetPage = () => setPage(1);

  return (
    <>
      <PageHeader
        title="ศูนย์เอกสาร"
        description="แสดงเฉพาะเอกสารที่คุณมีสิทธิ์เข้าถึง ระบบตรวจสิทธิ์ทุกครั้งที่เปิดหรือดาวน์โหลด"
        actions={has("documents:upload") ? <UploadDialog /> : null}
      />

      <div
        role="search"
        className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_11rem_10rem_9rem_auto_auto] lg:items-end"
      >
        <div className="space-y-1.5 sm:col-span-2 lg:col-span-1">
          <Label htmlFor={ids.q}>ค้นหา</Label>
          <div className="relative">
            <Search
              className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
              aria-hidden
            />
            <Input
              id={ids.q}
              type="search"
              placeholder={inContent ? "ถามหรือค้นหาข้อความในเอกสาร" : "ชื่อหรือคำอธิบายเอกสาร"}
              className="pl-8"
              value={search}
              maxLength={200}
              onChange={(e) => {
                setSearch(e.target.value);
                resetPage();
              }}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.category}>หมวดหมู่</Label>
          <NativeSelect
            id={ids.category}
            value={category}
            onChange={(e) => {
              setCategory(e.target.value as DocumentCategory | "");
              resetPage();
            }}
          >
            <option value="">ทุกหมวดหมู่</option>
            {categorySchema.options.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.visibility}>การมองเห็น</Label>
          <NativeSelect
            id={ids.visibility}
            value={visibility}
            onChange={(e) => {
              setVisibility(e.target.value as DocumentVisibility | "");
              resetPage();
            }}
          >
            <option value="">ทั้งหมด</option>
            {visibilitySchema.options.map((v) => (
              <option key={v} value={v}>
                {VISIBILITY_LABELS[v].label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.sort}>เรียงตาม</Label>
          <NativeSelect
            id={ids.sort}
            value={sort}
            onChange={(e) => setSort(e.target.value as typeof sort)}
          >
            <option value="updated">อัปเดตล่าสุด</option>
            <option value="created">สร้างล่าสุด</option>
            <option value="title">ชื่อ ก-ฮ</option>
          </NativeSelect>
        </div>
        <Button
          type="button"
          variant={inContent ? "default" : "outline"}
          aria-pressed={inContent}
          onClick={() => setInContent((v) => !v)}
        >
          <Sparkles aria-hidden />
          ค้นหาในเนื้อหา
        </Button>
        <Button
          type="button"
          variant={mine ? "default" : "outline"}
          aria-pressed={mine}
          onClick={() => {
            setMine((v) => !v);
            resetPage();
          }}
        >
          เอกสารของฉัน
        </Button>
      </div>

      {inContent ? (
        <ContentSearchResults query={q} />
      ) : list.isPending ? (
        <Card>
          <CardContent className="space-y-3" aria-busy="true" aria-label="กำลังโหลดรายการเอกสาร">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : list.isError ? (
        <ErrorState
          message={list.error.message}
          requestId={list.error instanceof ApiError ? list.error.requestId : null}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      ) : list.data.items.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={FileSearch}
            title="ไม่พบเอกสารที่ตรงกับเงื่อนไข"
            description="ลองเปลี่ยนคำค้นหรือตัวกรอง"
          />
        ) : (
          <EmptyState
            icon={FileText}
            title="ยังไม่มีเอกสารที่คุณเข้าถึงได้"
            description={
              has("documents:upload")
                ? "เริ่มต้นด้วยการอัปโหลดเอกสารแรกของคุณ"
                : "เมื่อมีผู้แชร์เอกสารให้คุณ เอกสารจะแสดงที่นี่"
            }
          />
        )
      ) : (
        <Card className="py-2">
          <CardContent className="px-2">
            <div className="text-muted-foreground hidden grid-cols-[minmax(0,1fr)_9rem_8rem_9rem] gap-4 px-3 py-2 text-xs font-medium md:grid">
              <span>เอกสาร</span>
              <span>หมวดหมู่</span>
              <span>การมองเห็น</span>
              <span className="text-right">สถานะ / อัปเดต</span>
            </div>
            <ul className="divide-y" aria-label="รายการเอกสาร">
              {list.data.items.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} />
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {!inContent && list.data && list.data.total > 0 ? (
        <nav
          aria-label="เลื่อนหน้า"
          className="mt-4 flex items-center justify-between gap-2 text-sm"
        >
          <span className="text-muted-foreground">
            ทั้งหมด {list.data.total.toLocaleString("th-TH")} รายการ
          </span>
          {totalPages > 1 ? (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft aria-hidden />
                ก่อนหน้า
              </Button>
              <span className="text-muted-foreground tabular-nums">
                หน้า {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                ถัดไป
                <ChevronRight aria-hidden />
              </Button>
            </div>
          ) : null}
        </nav>
      ) : null}
    </>
  );
}
