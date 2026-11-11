"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { FilePlus2, Loader2, Pencil, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { FormField } from "@/components/common/form-field";
import { NativeSelect } from "@/components/common/native-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FileDrop } from "@/features/documents/components/file-drop";
import {
  useDeleteDocument,
  useUpdateDocument,
  useUploadVersion,
} from "@/features/documents/hooks/use-documents";
import { CATEGORY_LABELS, STATUS_LABELS, VISIBILITY_LABELS } from "@/features/documents/labels";
import { documentMetaSchema } from "@/features/documents/schemas";
import { ApiError } from "@/services/api-client";
import {
  categorySchema,
  documentStatusSchema,
  visibilitySchema,
  type DocumentDetail,
  type DocumentStatus,
  type DocumentUpdateInput,
} from "@/services/documents";

function ErrorAlert({ error }: { error: unknown }) {
  if (!(error instanceof ApiError)) return null;
  return (
    <Alert variant="destructive">
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  );
}

const editSchema = documentMetaSchema.extend({ status: documentStatusSchema });
type EditValues = {
  title: string;
  description: string;
  category: DocumentDetail["category"];
  visibility: DocumentDetail["visibility"];
  status: DocumentStatus;
};

export function EditDocumentDialog({ doc }: { doc: DocumentDetail }) {
  const [open, setOpen] = useState(false);
  const ids = { description: useId(), category: useId(), status: useId(), visibility: useId() };
  const update = useUpdateDocument(doc.id);
  const canManage = doc.capabilities.can_manage;
  const values: EditValues = {
    title: doc.title,
    description: doc.description ?? "",
    category: doc.category,
    visibility: doc.visibility,
    status: doc.status,
  };
  const form = useForm<EditValues>({ resolver: zodResolver(editSchema), values });
  const visibility = useWatch({ control: form.control, name: "visibility" });

  const onSubmit = form.handleSubmit((v) => {
    const body: DocumentUpdateInput = {
      title: v.title,
      description: v.description || null,
      category: v.category,
      status: v.status,
    };
    // Visibility needs MANAGE; only send it when it changed.
    if (canManage && v.visibility !== doc.visibility) body.visibility = v.visibility;
    update.mutate(body, {
      onSuccess: () => {
        toast.success("บันทึกข้อมูลเอกสารแล้ว");
        setOpen(false);
      },
    });
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) update.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Pencil aria-hidden />
          แก้ไขข้อมูล
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>แก้ไขข้อมูลเอกสาร</DialogTitle>
          <DialogDescription>การแก้ไขจะถูกบันทึกในประวัติของเอกสาร</DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มแก้ไขเอกสาร">
          <ErrorAlert error={update.error} />
          <FormField
            label="ชื่อเอกสาร"
            registration={form.register("title")}
            error={form.formState.errors.title}
          />
          <div className="space-y-1.5">
            <Label htmlFor={ids.description}>คำอธิบาย</Label>
            <Textarea id={ids.description} rows={3} {...form.register("description")} />
            {form.formState.errors.description ? (
              <p role="alert" className="text-destructive text-xs">
                {form.formState.errors.description.message}
              </p>
            ) : null}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={ids.category}>หมวดหมู่</Label>
              <NativeSelect id={ids.category} {...form.register("category")}>
                {categorySchema.options.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABELS[c]}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.status}>สถานะ</Label>
              <NativeSelect id={ids.status} {...form.register("status")}>
                {documentStatusSchema.options.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          {canManage ? (
            <div className="space-y-1.5">
              <Label htmlFor={ids.visibility}>ผู้ที่เห็นเอกสาร</Label>
              <NativeSelect id={ids.visibility} {...form.register("visibility")}>
                {visibilitySchema.options
                  .filter((v) => v !== "DEPARTMENT" || doc.department)
                  .map((v) => (
                    <option key={v} value={v}>
                      {VISIBILITY_LABELS[v].label}
                    </option>
                  ))}
              </NativeSelect>
              <p className="text-muted-foreground text-xs">{VISIBILITY_LABELS[visibility].hint}</p>
            </div>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              บันทึก
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function NewVersionDialog({ doc }: { doc: DocumentDetail }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const upload = useUploadVersion(doc.id);
  const next = (doc.current_version?.version_number ?? 0) + 1;

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (upload.isPending) return;
        setOpen(value);
        if (!value) {
          setFile(null);
          upload.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <FilePlus2 aria-hidden />
          อัปโหลดเวอร์ชันใหม่
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>อัปโหลดฉบับที่ {next}</DialogTitle>
          <DialogDescription>
            ไฟล์ใหม่จะเป็นฉบับปัจจุบัน ฉบับเดิมยังดาวน์โหลดได้จากประวัติเวอร์ชัน
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <ErrorAlert error={upload.error} />
          <FileDrop file={file} onChange={setFile} disabled={upload.isPending} />
        </div>
        <DialogFooter>
          <Button
            disabled={!file || upload.isPending}
            onClick={() => {
              if (!file) return;
              upload.mutate(file, {
                onSuccess: () => {
                  toast.success(`อัปโหลดฉบับที่ ${next} แล้ว`);
                  setOpen(false);
                  setFile(null);
                },
              });
            }}
          >
            {upload.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            อัปโหลด
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function DeleteDocumentDialog({ doc }: { doc: DocumentDetail }) {
  const router = useRouter();
  const remove = useDeleteDocument(doc.id);
  return (
    <Dialog onOpenChange={(open) => !open && remove.reset()}>
      <DialogTrigger asChild>
        <Button variant="outline" className="text-destructive hover:text-destructive">
          <Trash2 aria-hidden />
          ลบเอกสาร
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>ลบเอกสาร “{doc.title}”?</DialogTitle>
          <DialogDescription>
            เอกสารจะหายไปจากรายการของทุกคนทันที ผู้ดูแลระบบยังตรวจสอบได้จากบันทึกการใช้งาน
          </DialogDescription>
        </DialogHeader>
        <ErrorAlert error={remove.error} />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">ยกเลิก</Button>
          </DialogClose>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(undefined, {
                onSuccess: () => {
                  toast.success("ลบเอกสารแล้ว");
                  router.replace("/documents");
                },
              })
            }
          >
            {remove.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ลบเอกสาร
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
