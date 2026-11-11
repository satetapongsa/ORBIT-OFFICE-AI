"use client";

import { ArrowLeft, Download, FileQuestion, Loader2, RotateCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AclEditor } from "@/features/documents/components/acl-editor";
import {
  DeleteDocumentDialog,
  EditDocumentDialog,
  NewVersionDialog,
} from "@/features/documents/components/document-dialogs";
import { ProcessingBadge } from "@/features/documents/components/processing-badge";
import {
  useDocument,
  useDocumentHistory,
  useDocumentText,
  useReprocessVersion,
} from "@/features/documents/hooks/use-documents";
import {
  ACCESS_LABELS,
  CATEGORY_LABELS,
  DOCUMENT_ACTION_LABELS,
  STATUS_LABELS,
  VISIBILITY_LABELS,
  formatBytes,
} from "@/features/documents/labels";
import { formatDateTime, formatRelative } from "@/lib/format";
import { ApiError } from "@/services/api-client";
import { downloadDocument, type DocumentDetail, type DocumentVersion } from "@/services/documents";

function useDownload(doc: DocumentDetail) {
  const [busy, setBusy] = useState<string | null>(null);
  const run = async (version?: DocumentVersion) => {
    const key = version?.id ?? "current";
    setBusy(key);
    try {
      await downloadDocument(doc.id, version?.id, version?.original_filename);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "ดาวน์โหลดไม่สำเร็จ");
    } finally {
      setBusy(null);
    }
  };
  return { busy, run };
}

function TextPreview({ doc }: { doc: DocumentDetail }) {
  const current = doc.versions.find((v) => v.id === doc.current_version?.id) ?? null;
  const ready = current?.processing_status === "READY";
  const text = useDocumentText(doc.id, current?.id ?? null, ready);
  const reprocess = useReprocessVersion(doc.id);

  return (
    <Card>
      <CardHeader>
        <CardTitle>เนื้อหาเอกสาร</CardTitle>
        <CardDescription>
          ข้อความที่ระบบดึงจากไฟล์ฉบับปัจจุบัน ใช้สำหรับค้นหาและผู้ช่วย AI ในเฟสถัดไป
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!current ? (
          <p className="text-muted-foreground text-sm">เอกสารนี้ยังไม่มีไฟล์</p>
        ) : current.processing_status === "PENDING" ||
          current.processing_status === "PROCESSING" ? (
          <div className="text-muted-foreground flex items-center gap-2 text-sm" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            ระบบกำลังประมวลผลไฟล์ หน้านี้จะอัปเดตอัตโนมัติ
          </div>
        ) : current.processing_status === "FAILED" ? (
          <Alert variant="destructive">
            <AlertTitle>ประมวลผลไฟล์ไม่สำเร็จ</AlertTitle>
            <AlertDescription className="space-y-3">
              <p>{current.processing_error ?? "ไม่ทราบสาเหตุ"}</p>
              {doc.capabilities.can_edit ? (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={reprocess.isPending}
                  onClick={() =>
                    reprocess.mutate(current.id, {
                      onSuccess: () => toast.success("ส่งไฟล์เข้าคิวประมวลผลใหม่แล้ว"),
                      onError: (e) =>
                        toast.error(
                          e instanceof ApiError ? e.message : "ไม่สามารถสั่งประมวลผลใหม่ได้",
                        ),
                    })
                  }
                >
                  <RotateCw aria-hidden />
                  ประมวลผลใหม่
                </Button>
              ) : null}
            </AlertDescription>
          </Alert>
        ) : text.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : text.isError ? (
          <p className="text-destructive text-sm">{text.error.message}</p>
        ) : text.data.char_count === 0 ? (
          <p className="text-muted-foreground text-sm">
            ไม่พบข้อความในไฟล์ (อาจเป็นเอกสารสแกนหรือรูปภาพ) ระบบยังไม่รองรับการอ่านข้อความจากภาพ
          </p>
        ) : (
          <>
            {/* Rendered as plain text: document content is untrusted and never interpreted. */}
            <pre
              data-testid="document-text"
              className="bg-muted/40 max-h-96 overflow-auto rounded-lg border p-4 font-sans text-sm leading-relaxed whitespace-pre-wrap"
            >
              {text.data.content}
            </pre>
            <p className="text-muted-foreground text-xs">
              {text.data.char_count.toLocaleString("th-TH")} ตัวอักษร
              {text.data.truncated ? " · แสดงเฉพาะส่วนต้น ดาวน์โหลดไฟล์เพื่ออ่านทั้งหมด" : ""}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Versions({ doc }: { doc: DocumentDetail }) {
  const download = useDownload(doc);
  return (
    <Card>
      <CardHeader>
        <CardTitle>ประวัติเวอร์ชัน</CardTitle>
        <CardDescription>{doc.versions.length} เวอร์ชัน</CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="divide-y">
          {doc.versions.map((v) => (
            <li
              key={v.id}
              className="flex flex-wrap items-center gap-3 py-3 text-sm"
              data-testid="version-row"
            >
              <div className="min-w-0 flex-1">
                <p className="font-medium">
                  ฉบับที่ {v.version_number}
                  {v.id === doc.current_version?.id ? (
                    <Badge variant="secondary" className="ml-2">
                      ปัจจุบัน
                    </Badge>
                  ) : null}
                </p>
                <p className="text-muted-foreground truncate text-xs">
                  {v.original_filename} · {formatBytes(v.size_bytes)}
                  {v.page_count ? ` · ${v.page_count} หน้า` : ""} ·{" "}
                  {v.uploaded_by?.display_name ?? "ไม่ทราบผู้อัปโหลด"} ·{" "}
                  <time dateTime={v.created_at} title={formatDateTime(v.created_at)}>
                    {formatRelative(v.created_at)}
                  </time>
                </p>
              </div>
              <ProcessingBadge status={v.processing_status} />
              <Button
                variant="ghost"
                size="sm"
                aria-label={`ดาวน์โหลดฉบับที่ ${v.version_number}`}
                disabled={download.busy !== null}
                onClick={() => void download.run(v)}
              >
                {download.busy === v.id ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <Download aria-hidden />
                )}
              </Button>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function History({ doc }: { doc: DocumentDetail }) {
  const history = useDocumentHistory(doc.id, true);
  return (
    <Card>
      <CardHeader>
        <CardTitle>ประวัติการใช้งาน</CardTitle>
        <CardDescription>จากบันทึกการใช้งานระบบ (100 รายการล่าสุด)</CardDescription>
      </CardHeader>
      <CardContent>
        {history.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : history.isError ? (
          <p className="text-destructive text-sm">{history.error.message}</p>
        ) : history.data.length === 0 ? (
          <p className="text-muted-foreground text-sm">ยังไม่มีประวัติ</p>
        ) : (
          <ol className="max-h-80 space-y-3 overflow-y-auto" data-testid="document-history">
            {history.data.map((item) => {
              const version =
                typeof item.details.version === "number" ? item.details.version : null;
              return (
                <li key={item.id} className="text-sm">
                  <p>
                    {DOCUMENT_ACTION_LABELS[item.action] ?? item.action}
                    {version ? ` (ฉบับที่ ${version})` : ""}
                    <span className="text-muted-foreground">
                      {" "}
                      · {item.actor?.display_name ?? "ระบบ"}
                    </span>
                  </p>
                  <time
                    dateTime={item.occurred_at}
                    title={formatDateTime(item.occurred_at)}
                    className="text-muted-foreground text-xs"
                  >
                    {formatRelative(item.occurred_at)}
                  </time>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="กำลังโหลดเอกสาร">
      <Skeleton className="h-8 w-72" />
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-80 rounded-xl lg:col-span-2" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    </div>
  );
}

export function DocumentDetailView({ id }: { id: string }) {
  const query = useDocument(id);

  if (query.isPending) return <DetailSkeleton />;
  if (query.isError) {
    const error = query.error;
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return (
        <EmptyState
          icon={FileQuestion}
          title="ไม่พบเอกสาร หรือคุณไม่มีสิทธิ์เข้าถึง"
          description="เอกสารอาจถูกลบ หรือเจ้าของยังไม่ได้แชร์ให้คุณ"
          action={
            <Button asChild variant="outline">
              <Link href="/documents">กลับไปศูนย์เอกสาร</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        message={error.message}
        requestId={error instanceof ApiError ? error.requestId : null}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }

  return <DocumentDetailContent doc={query.data} />;
}

function DocumentDetailContent({ doc }: { doc: DocumentDetail }) {
  const download = useDownload(doc);
  const caps = doc.capabilities;
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Link
          href="/documents"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          <ArrowLeft className="size-4" aria-hidden />
          ศูนย์เอกสาร
        </Link>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight break-words">{doc.title}</h1>
            <div className="flex flex-wrap gap-1.5">
              <Badge variant="secondary">{CATEGORY_LABELS[doc.category]}</Badge>
              <Badge variant="outline">{VISIBILITY_LABELS[doc.visibility].label}</Badge>
              {doc.status !== "ACTIVE" ? (
                <Badge variant="outline">{STATUS_LABELS[doc.status]}</Badge>
              ) : null}
              {doc.current_version ? (
                <ProcessingBadge status={doc.current_version.processing_status} />
              ) : null}
            </div>
            {doc.description ? (
              <p className="text-muted-foreground max-w-3xl text-sm whitespace-pre-line">
                {doc.description}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {doc.current_version ? (
              <Button disabled={download.busy !== null} onClick={() => void download.run()}>
                {download.busy ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <Download aria-hidden />
                )}
                ดาวน์โหลด
              </Button>
            ) : null}
            {caps.can_upload_version ? <NewVersionDialog doc={doc} /> : null}
            {caps.can_edit ? <EditDocumentDialog doc={doc} /> : null}
            {caps.can_delete ? <DeleteDocumentDialog doc={doc} /> : null}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="min-w-0 space-y-4 lg:col-span-2">
          <TextPreview doc={doc} />
          <Versions doc={doc} />
        </div>
        <div className="min-w-0 space-y-4">
          <Card data-testid="document-info">
            <CardHeader>
              <CardTitle>ข้อมูลเอกสาร</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-2 text-sm">
                <dt className="text-muted-foreground">เจ้าของ</dt>
                <dd>{doc.owner.display_name}</dd>
                <dt className="text-muted-foreground">แผนก</dt>
                <dd>{doc.department?.name ?? "—"}</dd>
                <dt className="text-muted-foreground">สิทธิ์ของคุณ</dt>
                <dd>{ACCESS_LABELS[doc.access_level]}</dd>
                <dt className="text-muted-foreground">สร้างเมื่อ</dt>
                <dd>{formatDateTime(doc.created_at)}</dd>
                <dt className="text-muted-foreground">อัปเดตล่าสุด</dt>
                <dd>{formatDateTime(doc.updated_at)}</dd>
              </dl>
            </CardContent>
          </Card>
          {caps.can_manage_access ? <AclEditor doc={doc} /> : null}
          {caps.can_view_history ? <History doc={doc} /> : null}
        </div>
      </div>
    </div>
  );
}
