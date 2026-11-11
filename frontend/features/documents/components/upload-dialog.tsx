"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Upload } from "lucide-react";
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
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/features/auth/hooks/use-session";
import { FileDrop } from "@/features/documents/components/file-drop";
import { useUploadDocument } from "@/features/documents/hooks/use-documents";
import { CATEGORY_LABELS, VISIBILITY_LABELS } from "@/features/documents/labels";
import {
  documentMetaSchema,
  titleFromFilename,
  type DocumentMetaValues,
} from "@/features/documents/schemas";
import { ApiError } from "@/services/api-client";
import { categorySchema, visibilitySchema } from "@/services/documents";

export function UploadDialog() {
  const router = useRouter();
  const { me } = useSession();
  const hasDepartment = Boolean(me?.user.department);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileMissing, setFileMissing] = useState(false);
  const ids = { description: useId(), category: useId(), visibility: useId() };
  const upload = useUploadDocument();
  const defaults: DocumentMetaValues = {
    title: "",
    description: "",
    category: "OTHER",
    visibility: hasDepartment ? "DEPARTMENT" : "PRIVATE",
  };
  const form = useForm<DocumentMetaValues>({
    resolver: zodResolver(documentMetaSchema),
    defaultValues: defaults,
  });
  const visibility = useWatch({ control: form.control, name: "visibility" });
  const error = upload.error instanceof ApiError ? upload.error : null;

  const reset = () => {
    form.reset(defaults);
    setFile(null);
    setFileMissing(false);
    upload.reset();
  };

  const onSubmit = form.handleSubmit((values) => {
    if (!file) {
      setFileMissing(true);
      return;
    }
    upload.mutate(
      { ...values, file },
      {
        onSuccess: (detail) => {
          toast.success("อัปโหลดเอกสารแล้ว ระบบกำลังประมวลผลข้อความ");
          setOpen(false);
          reset();
          router.push(`/documents/${detail.id}`);
        },
      },
    );
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (upload.isPending) return;
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Upload aria-hidden />
          อัปโหลดเอกสาร
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>อัปโหลดเอกสาร</DialogTitle>
          <DialogDescription>
            ระบบตรวจชนิดไฟล์จากเนื้อหาจริง และดึงข้อความออกมาเพื่อใช้ค้นหา
          </DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มอัปโหลดเอกสาร">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          ) : null}
          <div className="space-y-1.5">
            <FileDrop
              file={file}
              disabled={upload.isPending}
              onChange={(next) => {
                setFile(next);
                setFileMissing(false);
                if (next && !form.getValues("title")) {
                  form.setValue("title", titleFromFilename(next.name), { shouldValidate: true });
                }
              }}
            />
            {fileMissing ? (
              <p role="alert" className="text-destructive text-xs">
                กรุณาเลือกไฟล์
              </p>
            ) : null}
          </div>
          <FormField
            label="ชื่อเอกสาร"
            registration={form.register("title")}
            error={form.formState.errors.title}
            disabled={upload.isPending}
          />
          <div className="space-y-1.5">
            <Label htmlFor={ids.description}>คำอธิบาย (ไม่บังคับ)</Label>
            <Textarea
              id={ids.description}
              rows={3}
              disabled={upload.isPending}
              aria-invalid={form.formState.errors.description ? true : undefined}
              {...form.register("description")}
            />
            {form.formState.errors.description ? (
              <p role="alert" className="text-destructive text-xs">
                {form.formState.errors.description.message}
              </p>
            ) : null}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={ids.category}>หมวดหมู่</Label>
              <NativeSelect
                id={ids.category}
                disabled={upload.isPending}
                {...form.register("category")}
              >
                {categorySchema.options.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABELS[c]}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.visibility}>ผู้ที่เห็นเอกสาร</Label>
              <NativeSelect
                id={ids.visibility}
                disabled={upload.isPending}
                {...form.register("visibility")}
              >
                {visibilitySchema.options
                  .filter((v) => v !== "DEPARTMENT" || hasDepartment)
                  .map((v) => (
                    <option key={v} value={v}>
                      {VISIBILITY_LABELS[v].label}
                    </option>
                  ))}
              </NativeSelect>
              <p className="text-muted-foreground text-xs">{VISIBILITY_LABELS[visibility].hint}</p>
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={upload.isPending}>
              {upload.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {upload.isPending ? "กำลังอัปโหลด…" : "อัปโหลด"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
