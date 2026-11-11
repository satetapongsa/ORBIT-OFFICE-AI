"use client";

import { Building2, Loader2, Plus, Shield, Trash2, User } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/common/native-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import {
  useDepartments,
  useDirectorySearch,
  useDocumentAcl,
  useReplaceAcl,
  useRoles,
} from "@/features/documents/hooks/use-documents";
import { ACCESS_LABELS, PRINCIPAL_LABELS, VISIBILITY_LABELS } from "@/features/documents/labels";
import { ApiError } from "@/services/api-client";
import {
  accessLevelSchema,
  type AccessLevel,
  type DocumentDetail,
  type PrincipalType,
} from "@/services/documents";

interface DraftEntry {
  principal_type: PrincipalType;
  principal_id: string;
  principal_name: string;
  access_level: AccessLevel;
}

const ICONS = { USER: User, DEPARTMENT: Building2, ROLE: Shield } as const;

function sameEntries(a: DraftEntry[], b: DraftEntry[]): boolean {
  const key = (e: DraftEntry) => `${e.principal_type}:${e.principal_id}:${e.access_level}`;
  return a.map(key).sort().join("|") === b.map(key).sort().join("|");
}

function LevelSelect({
  value,
  onChange,
  label,
}: {
  value: AccessLevel;
  onChange: (v: AccessLevel) => void;
  label: string;
}) {
  return (
    <NativeSelect
      aria-label={label}
      className="w-32 shrink-0"
      value={value}
      onChange={(e) => onChange(e.target.value as AccessLevel)}
    >
      {accessLevelSchema.options.map((level) => (
        <option key={level} value={level}>
          {ACCESS_LABELS[level]}
        </option>
      ))}
    </NativeSelect>
  );
}

export function AclEditor({ doc }: { doc: DocumentDetail }) {
  const { has } = useSession();
  const acl = useDocumentAcl(doc.id, true);
  const save = useReplaceAcl(doc.id);
  const [draft, setDraft] = useState<DraftEntry[] | null>(null);
  const ids = { type: useId(), search: useId(), pick: useId(), level: useId() };

  const allowedTypes: PrincipalType[] = [
    ...(has("employees:read_directory") ? (["USER"] as const) : []),
    ...(has("departments:read") ? (["DEPARTMENT"] as const) : []),
    ...(has("roles:read") ? (["ROLE"] as const) : []),
  ];
  const [type, setType] = useState<PrincipalType>(allowedTypes[0] ?? "USER");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<{ id: string; name: string } | null>(null);
  const [level, setLevel] = useState<AccessLevel>("VIEW");

  const directory = useDirectorySearch(query.trim(), type === "USER" && query.trim().length > 0);
  const departments = useDepartments(type === "DEPARTMENT");
  const roles = useRoles(type === "ROLE");

  const saved: DraftEntry[] = (acl.data?.entries ?? []).map((e) => ({
    principal_type: e.principal_type,
    principal_id: e.principal_id,
    principal_name: e.principal_name,
    access_level: e.access_level,
  }));
  const entries = draft ?? saved;
  const dirty = draft !== null && !sameEntries(draft, saved);

  const add = () => {
    if (!picked) return;
    const exists = entries.some((e) => e.principal_type === type && e.principal_id === picked.id);
    if (picked.id === doc.owner.id && type === "USER") {
      toast.error("เจ้าของเอกสารมีสิทธิ์เต็มอยู่แล้ว");
      return;
    }
    setDraft(
      exists
        ? entries.map((e) =>
            e.principal_type === type && e.principal_id === picked.id
              ? { ...e, access_level: level }
              : e,
          )
        : [
            ...entries,
            {
              principal_type: type,
              principal_id: picked.id,
              principal_name: picked.name,
              access_level: level,
            },
          ],
    );
    setPicked(null);
    setQuery("");
  };

  const error = save.error instanceof ApiError ? save.error : null;

  return (
    <Card data-testid="acl-editor">
      <CardHeader>
        <CardTitle>การแชร์และสิทธิ์</CardTitle>
        <CardDescription>
          {VISIBILITY_LABELS[doc.visibility].label}: {VISIBILITY_LABELS[doc.visibility].hint}{" "}
          เจ้าของ ({doc.owner.display_name}) มีสิทธิ์เต็มเสมอ
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {acl.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : acl.isError ? (
          <p className="text-destructive text-sm">{acl.error.message}</p>
        ) : (
          <>
            {entries.length === 0 ? (
              <p className="text-muted-foreground text-sm">ยังไม่ได้แชร์ให้ผู้ใดเพิ่มเติม</p>
            ) : (
              <ul className="space-y-2" aria-label="ผู้ได้รับสิทธิ์">
                {entries.map((entry) => {
                  const Icon = ICONS[entry.principal_type];
                  return (
                    <li
                      key={`${entry.principal_type}:${entry.principal_id}`}
                      className="flex items-center gap-2 text-sm"
                      data-testid="acl-entry"
                    >
                      <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
                      <span className="min-w-0 flex-1 truncate">
                        {entry.principal_name}
                        <span className="text-muted-foreground">
                          {" "}
                          ({PRINCIPAL_LABELS[entry.principal_type]})
                        </span>
                      </span>
                      <LevelSelect
                        label={`ระดับสิทธิ์ของ ${entry.principal_name}`}
                        value={entry.access_level}
                        onChange={(value) =>
                          setDraft(
                            entries.map((e) => (e === entry ? { ...e, access_level: value } : e)),
                          )
                        }
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={`ลบสิทธิ์ของ ${entry.principal_name}`}
                        onClick={() => setDraft(entries.filter((e) => e !== entry))}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}

            {allowedTypes.length > 0 ? (
              <div className="bg-muted/30 space-y-3 rounded-lg border p-3">
                <div className="grid gap-3 sm:grid-cols-[8rem_minmax(0,1fr)]">
                  <div className="space-y-1.5">
                    <Label htmlFor={ids.type}>แชร์ให้</Label>
                    <NativeSelect
                      id={ids.type}
                      value={type}
                      onChange={(e) => {
                        setType(e.target.value as PrincipalType);
                        setPicked(null);
                        setQuery("");
                      }}
                    >
                      {allowedTypes.map((t) => (
                        <option key={t} value={t}>
                          {PRINCIPAL_LABELS[t]}
                        </option>
                      ))}
                    </NativeSelect>
                  </div>
                  {type === "USER" ? (
                    <div className="space-y-1.5">
                      <Label htmlFor={ids.search}>ค้นหาเพื่อนร่วมงาน</Label>
                      <Input
                        id={ids.search}
                        type="search"
                        placeholder="พิมพ์ชื่อหรือตำแหน่ง"
                        value={picked ? picked.name : query}
                        onChange={(e) => {
                          setPicked(null);
                          setQuery(e.target.value);
                        }}
                      />
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      <Label htmlFor={ids.pick}>{PRINCIPAL_LABELS[type]}</Label>
                      <NativeSelect
                        id={ids.pick}
                        value={picked?.id ?? ""}
                        onChange={(e) => {
                          const list =
                            (type === "DEPARTMENT" ? departments.data : roles.data) ?? [];
                          const found = list.find((item) => item.id === e.target.value);
                          setPicked(found ? { id: found.id, name: found.name } : null);
                        }}
                      >
                        <option value="">เลือก{PRINCIPAL_LABELS[type]}</option>
                        {((type === "DEPARTMENT" ? departments.data : roles.data) ?? []).map(
                          (item) => (
                            <option key={item.id} value={item.id}>
                              {item.name}
                            </option>
                          ),
                        )}
                      </NativeSelect>
                    </div>
                  )}
                </div>
                {type === "USER" && !picked && query.trim() ? (
                  <ul
                    className="bg-background max-h-48 overflow-y-auto rounded-md border"
                    aria-label="ผลการค้นหา"
                  >
                    {directory.isPending ? (
                      <li className="text-muted-foreground p-2 text-sm">กำลังค้นหา…</li>
                    ) : directory.data && directory.data.length > 0 ? (
                      directory.data.map((u) => (
                        <li key={u.id}>
                          <button
                            type="button"
                            className="hover:bg-muted w-full px-3 py-2 text-left text-sm"
                            onClick={() => setPicked({ id: u.id, name: u.display_name })}
                          >
                            <span className="font-medium">{u.display_name}</span>
                            <span className="text-muted-foreground block text-xs">
                              {[u.job_title, u.department?.name].filter(Boolean).join(" · ") || "—"}
                            </span>
                          </button>
                        </li>
                      ))
                    ) : (
                      <li className="text-muted-foreground p-2 text-sm">ไม่พบผู้ใช้</li>
                    )}
                  </ul>
                ) : null}
                <div className="flex items-end justify-end gap-2">
                  <div className="space-y-1.5">
                    <Label htmlFor={ids.level}>ระดับสิทธิ์</Label>
                    <NativeSelect
                      id={ids.level}
                      className="w-32"
                      value={level}
                      onChange={(e) => setLevel(e.target.value as AccessLevel)}
                    >
                      {accessLevelSchema.options.map((l) => (
                        <option key={l} value={l}>
                          {ACCESS_LABELS[l]}
                        </option>
                      ))}
                    </NativeSelect>
                  </div>
                  <Button type="button" variant="outline" disabled={!picked} onClick={add}>
                    <Plus aria-hidden />
                    เพิ่ม
                  </Button>
                </div>
              </div>
            ) : null}

            {error ? (
              <Alert variant="destructive">
                <AlertDescription>
                  {error.message}
                  {error.details.length > 0
                    ? `: ${error.details.map((d) => d.message).join(", ")}`
                    : ""}
                </AlertDescription>
              </Alert>
            ) : null}
            <div className="flex justify-end gap-2">
              {dirty ? (
                <Button type="button" variant="ghost" onClick={() => setDraft(null)}>
                  ยกเลิกการเปลี่ยนแปลง
                </Button>
              ) : null}
              <Button
                type="button"
                disabled={!dirty || save.isPending}
                onClick={() =>
                  save.mutate(
                    entries.map(({ principal_type, principal_id, access_level }) => ({
                      principal_type,
                      principal_id,
                      access_level,
                    })),
                    {
                      onSuccess: () => {
                        setDraft(null);
                        toast.success("บันทึกสิทธิ์การเข้าถึงแล้ว");
                      },
                    },
                  )
                }
              >
                {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                บันทึกสิทธิ์
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
