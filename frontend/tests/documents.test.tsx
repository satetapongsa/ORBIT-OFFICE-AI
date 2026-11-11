import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AclEditor } from "@/features/documents/components/acl-editor";
import { DocumentDetailView } from "@/features/documents/components/document-detail-view";
import { DocumentsView } from "@/features/documents/components/documents-view";
import { checkFile } from "@/features/documents/labels";
import { titleFromFilename } from "@/features/documents/schemas";
import { CSRF_HEADER, filenameFromDisposition } from "@/services/api-client";
import type { DocumentDetail, DocumentListItem } from "@/services/documents";

import { createWrapper, json, mockApi } from "./fixtures";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/documents",
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

let permissions = new Set<string>();
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({
    me: { user: { id: "u-owner", department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" } } },
    has: (p: string) => permissions.has(p),
  }),
}));

const listItem = (overrides: Partial<DocumentListItem> = {}): DocumentListItem => ({
  id: "doc-1",
  title: "นโยบายการลา",
  description: null,
  category: "POLICY",
  visibility: "DEPARTMENT",
  status: "ACTIVE",
  owner: { id: "u-owner", display_name: "เอกชัย พนักงาน" },
  department: { id: "d-1", code: "SALES", name: "ฝ่ายขาย" },
  current_version: {
    id: "v-1",
    version_number: 1,
    original_filename: "leave.pdf",
    file_type: "PDF",
    size_bytes: 2048,
    processing_status: "READY",
  },
  created_at: "2026-11-11T05:00:00Z",
  updated_at: "2026-11-11T05:00:00Z",
  ...overrides,
});

const detail = (overrides: Partial<DocumentDetail> = {}): DocumentDetail => ({
  ...listItem(),
  access_level: "MANAGE",
  capabilities: {
    can_edit: true,
    can_manage: true,
    can_delete: false,
    can_manage_access: true,
    can_upload_version: true,
    can_view_history: true,
  },
  versions: [
    {
      id: "v-1",
      version_number: 1,
      original_filename: "leave.pdf",
      file_type: "PDF",
      size_bytes: 2048,
      processing_status: "READY",
      mime_type: "application/pdf",
      sha256: "abc",
      uploaded_by: { id: "u-owner", display_name: "เอกชัย พนักงาน" },
      processing_error: null,
      page_count: 3,
      char_count: 120,
      processed_at: "2026-11-11T05:00:05Z",
      created_at: "2026-11-11T05:00:00Z",
    },
  ],
  ...overrides,
});

beforeEach(() => {
  permissions = new Set([
    "documents:read",
    "documents:upload",
    "employees:read_directory",
    "departments:read",
  ]);
  push.mockReset();
  document.cookie = "aura_csrf=csrf-token; path=/";
});

describe("helpers", () => {
  it("parses RFC 5987 Thai filenames", () => {
    const header = `attachment; filename="plan.txt"; filename*=UTF-8''${encodeURIComponent("แผนงาน.txt")}`;
    expect(filenameFromDisposition(header, "x")).toBe("แผนงาน.txt");
    expect(filenameFromDisposition('attachment; filename="a.pdf"', "x")).toBe("a.pdf");
    expect(filenameFromDisposition(null, "fallback")).toBe("fallback");
  });

  it("pre-checks files and derives titles", () => {
    expect(checkFile(new File(["x"], "a.exe"))).toMatch("รองรับเฉพาะ");
    expect(checkFile(new File([""], "a.txt"))).toBe("ไฟล์ว่างเปล่า");
    expect(checkFile(new File(["x"], "A.PDF"))).toBeNull();
    expect(titleFromFilename("รายงาน_ประจำปี.final.pdf")).toBe("รายงาน ประจำปี.final");
  });
});

describe("DocumentsView", () => {
  it("lists accessible documents and sends search filters", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/documents": () =>
        json({ items: [listItem()], total: 1, page: 1, page_size: 20 }),
    });
    render(<DocumentsView />, { wrapper: createWrapper() });

    const row = await screen.findByTestId("document-row");
    expect(row).toHaveTextContent("นโยบายการลา");
    expect(row).toHaveTextContent("พร้อมใช้งาน");
    expect(within(row).getByRole("link")).toHaveAttribute("href", "/documents/doc-1");
    expect(screen.getByRole("button", { name: "อัปโหลดเอกสาร" })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("ค้นหา"), "ลา");
    await userEvent.selectOptions(screen.getByLabelText("หมวดหมู่"), "POLICY");
    await vi.waitFor(() => {
      const urls = fetchMock.mock.calls.map(([input]) => decodeURIComponent(String(input)));
      expect(urls.some((u) => u.includes("q=ลา") && u.includes("category=POLICY"))).toBe(true);
    });
  });

  it("hides upload without permission and explains the empty state", async () => {
    permissions = new Set(["documents:read"]);
    mockApi({
      "GET /api/v1/documents": () => json({ items: [], total: 0, page: 1, page_size: 20 }),
    });
    render(<DocumentsView />, { wrapper: createWrapper() });
    expect(await screen.findByText("ยังไม่มีเอกสารที่คุณเข้าถึงได้")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "อัปโหลดเอกสาร" })).not.toBeInTheDocument();
  });

  it("uploads a file as multipart with CSRF and opens the new document", async () => {
    let sent: FormData | null = null;
    let csrf: string | null = null;
    mockApi({
      "GET /api/v1/documents": () => json({ items: [], total: 0, page: 1, page_size: 20 }),
      "POST /api/v1/documents": (_, init) => {
        sent = init?.body as FormData;
        csrf = new Headers(init?.headers).get(CSRF_HEADER);
        return json(detail({ id: "doc-9" }), 201);
      },
    });
    render(<DocumentsView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "อัปโหลดเอกสาร" }));
    const dialog = await screen.findByRole("dialog");

    const file = new File(["เนื้อหา"], "คู่มือ_พนักงาน.txt", { type: "text/plain" });
    await userEvent.upload(within(dialog).getByLabelText("เลือกไฟล์เอกสาร"), file);
    expect(within(dialog).getByLabelText("ชื่อเอกสาร")).toHaveValue("คู่มือ พนักงาน");
    await userEvent.selectOptions(within(dialog).getByLabelText("หมวดหมู่"), "MANUAL");
    await userEvent.click(within(dialog).getByRole("button", { name: "อัปโหลด" }));

    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/documents/doc-9"));
    expect(csrf).toBe("csrf-token");
    const form = sent as unknown as FormData;
    expect(form.get("title")).toBe("คู่มือ พนักงาน");
    expect(form.get("category")).toBe("MANUAL");
    expect(form.get("visibility")).toBe("DEPARTMENT"); // default when the user has a department
    expect((form.get("file") as File).name).toBe("คู่มือ_พนักงาน.txt");
  });

  it("shows the server's validation message when a file is rejected", async () => {
    mockApi({
      "GET /api/v1/documents": () => json({ items: [], total: 0, page: 1, page_size: 20 }),
      "POST /api/v1/documents": () =>
        json(
          {
            error: {
              code: "unsupported_file_type",
              message: "เนื้อหาไฟล์ไม่ตรงกับนามสกุลไฟล์",
              details: [],
            },
          },
          415,
        ),
    });
    render(<DocumentsView />, { wrapper: createWrapper() });
    await userEvent.click(await screen.findByRole("button", { name: "อัปโหลดเอกสาร" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.upload(
      within(dialog).getByLabelText("เลือกไฟล์เอกสาร"),
      new File(["%PDF"], "fake.txt", { type: "text/plain" }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "อัปโหลด" }));
    expect(await within(dialog).findByText("เนื้อหาไฟล์ไม่ตรงกับนามสกุลไฟล์")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});

describe("DocumentDetailView", () => {
  it("renders extracted text as plain text and every management section for managers", async () => {
    mockApi({
      "GET /api/v1/documents/doc-1": () => json(detail()),
      "GET /api/v1/documents/doc-1/text": () =>
        json({
          version_id: "v-1",
          version_number: 1,
          content: '<img src=x onerror="alert(1)"> วันลา 10 วัน',
          char_count: 40,
          truncated: false,
        }),
      "GET /api/v1/documents/doc-1/acl": () =>
        json({ visibility: "DEPARTMENT", owner: detail().owner, entries: [] }),
      "GET /api/v1/documents/doc-1/history": () =>
        json([
          {
            id: "h1",
            action: "document.uploaded",
            occurred_at: "2026-11-11T05:00:00Z",
            actor: { id: "u-owner", display_name: "เอกชัย พนักงาน" },
            details: { version: 1 },
          },
        ]),
    });
    render(<DocumentDetailView id="doc-1" />, { wrapper: createWrapper() });

    const text = await screen.findByTestId("document-text");
    expect(text).toHaveTextContent('<img src=x onerror="alert(1)"> วันลา 10 วัน');
    expect(text.querySelector("img")).toBeNull(); // never interpreted as HTML
    expect(screen.getByRole("button", { name: "แก้ไขข้อมูล" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "อัปโหลดเวอร์ชันใหม่" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ลบเอกสาร" })).not.toBeInTheDocument();
    expect(await screen.findByTestId("acl-editor")).toBeInTheDocument();
    expect(await screen.findByTestId("document-history")).toHaveTextContent(
      "อัปโหลดเอกสาร (ฉบับที่ 1)",
    );
    expect(screen.getByTestId("version-row")).toHaveTextContent("3 หน้า");
  });

  it("hides actions a viewer may not use", async () => {
    const fetchMock = mockApi({
      "GET /api/v1/documents/doc-1": () =>
        json(
          detail({
            access_level: "VIEW",
            capabilities: {
              can_edit: false,
              can_manage: false,
              can_delete: false,
              can_manage_access: false,
              can_upload_version: false,
              can_view_history: false,
            },
          }),
        ),
      "GET /api/v1/documents/doc-1/text": () =>
        json({
          version_id: "v-1",
          version_number: 1,
          content: "x",
          char_count: 1,
          truncated: false,
        }),
    });
    render(<DocumentDetailView id="doc-1" />, { wrapper: createWrapper() });
    expect(await screen.findByRole("button", { name: "ดาวน์โหลด" })).toBeInTheDocument();
    for (const name of ["แก้ไขข้อมูล", "อัปโหลดเวอร์ชันใหม่", "ลบเอกสาร"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByTestId("acl-editor")).not.toBeInTheDocument();
    expect(screen.getByTestId("document-info")).toHaveTextContent("ดูได้");
    const urls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(urls.some((u) => u.includes("/acl") || u.includes("/history"))).toBe(false);
  });

  it("explains failed processing and offers a retry to editors", async () => {
    const failed = detail();
    failed.current_version = { ...failed.current_version!, processing_status: "FAILED" };
    failed.versions = [
      {
        ...failed.versions[0]!,
        processing_status: "FAILED",
        processing_error: "ไฟล์ PDF เสียหายหรืออ่านไม่ได้",
      },
    ];
    let retried = false;
    mockApi({
      "GET /api/v1/documents/doc-1": () => json(failed),
      "GET /api/v1/documents/doc-1/acl": () =>
        json({ visibility: "DEPARTMENT", owner: failed.owner, entries: [] }),
      "GET /api/v1/documents/doc-1/history": () => json([]),
      "POST /api/v1/documents/doc-1/versions/v-1/reprocess": () => {
        retried = true;
        return json(detail(), 202);
      },
    });
    render(<DocumentDetailView id="doc-1" />, { wrapper: createWrapper() });
    expect(await screen.findByText("ไฟล์ PDF เสียหายหรืออ่านไม่ได้")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "ประมวลผลใหม่" }));
    await vi.waitFor(() => expect(retried).toBe(true));
  });

  it("shows a not-found state without revealing whether the document exists", async () => {
    mockApi({
      "GET /api/v1/documents/doc-x": () =>
        json({ error: { code: "not_found", message: "ไม่พบเอกสาร", details: [] } }, 404),
    });
    render(<DocumentDetailView id="doc-x" />, { wrapper: createWrapper() });
    expect(await screen.findByText("ไม่พบเอกสาร หรือคุณไม่มีสิทธิ์เข้าถึง")).toBeInTheDocument();
  });
});

describe("AclEditor", () => {
  it("adds a colleague found in the directory and saves the grants", async () => {
    let body: unknown = null;
    mockApi({
      "GET /api/v1/documents/doc-1/acl": () =>
        json({ visibility: "PRIVATE", owner: detail().owner, entries: [] }),
      "GET /api/v1/directory/users": () =>
        json([
          { id: "u-2", display_name: "มานพ ผู้จัดการ", job_title: "ผู้จัดการ", department: null },
        ]),
      "PUT /api/v1/documents/doc-1/acl": (_, init) => {
        body = JSON.parse(String(init?.body));
        return json({
          visibility: "PRIVATE",
          owner: detail().owner,
          entries: [
            {
              id: "a1",
              principal_type: "USER",
              principal_id: "u-2",
              principal_name: "มานพ ผู้จัดการ",
              access_level: "EDIT",
              granted_by: null,
              created_at: "2026-11-11T05:00:00Z",
            },
          ],
        });
      },
    });
    render(<AclEditor doc={detail({ visibility: "PRIVATE" })} />, { wrapper: createWrapper() });
    expect(await screen.findByText("ยังไม่ได้แชร์ให้ผู้ใดเพิ่มเติม")).toBeInTheDocument();
    // Only principal types the user can look up are offered (no roles:read here).
    const typeSelect = screen.getByLabelText("แชร์ให้");
    expect(within(typeSelect).queryByText("บทบาท")).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("ค้นหาเพื่อนร่วมงาน"), "มานพ");
    await userEvent.click(await screen.findByRole("button", { name: /มานพ ผู้จัดการ/ }));
    await userEvent.selectOptions(screen.getByLabelText("ระดับสิทธิ์"), "EDIT");
    await userEvent.click(screen.getByRole("button", { name: "เพิ่ม" }));
    expect(screen.getByTestId("acl-entry")).toHaveTextContent("มานพ ผู้จัดการ");
    await userEvent.click(screen.getByRole("button", { name: "บันทึกสิทธิ์" }));

    await vi.waitFor(() =>
      expect(body).toEqual({
        entries: [{ principal_type: "USER", principal_id: "u-2", access_level: "EDIT" }],
      }),
    );
  });
});
