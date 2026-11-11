import type {
  AccessLevel,
  DocumentCategory,
  DocumentStatus,
  DocumentVisibility,
  IndexStatus,
  PrincipalType,
  ProcessingStatus,
} from "@/services/documents";

export const CATEGORY_LABELS: Record<DocumentCategory, string> = {
  POLICY: "นโยบาย",
  PROCEDURE: "ขั้นตอนการปฏิบัติงาน",
  FORM: "แบบฟอร์ม",
  REPORT: "รายงาน",
  CONTRACT: "สัญญา",
  MANUAL: "คู่มือ",
  OTHER: "อื่นๆ",
};

export const VISIBILITY_LABELS: Record<DocumentVisibility, { label: string; hint: string }> = {
  PRIVATE: { label: "ส่วนตัว", hint: "เห็นเฉพาะคุณและผู้ที่ได้รับสิทธิ์" },
  DEPARTMENT: { label: "ภายในแผนก", hint: "ทุกคนในแผนกของเอกสารดูได้" },
  COMPANY: { label: "ทั้งบริษัท", hint: "พนักงานทุกคนดูได้" },
  RESTRICTED: { label: "จำกัดสิทธิ์", hint: "เฉพาะผู้ที่ได้รับสิทธิ์โดยตรง" },
};

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  DRAFT: "ฉบับร่าง",
  ACTIVE: "ใช้งาน",
  ARCHIVED: "เก็บถาวร",
};

export const PROCESSING_LABELS: Record<ProcessingStatus, string> = {
  PENDING: "รอประมวลผล",
  PROCESSING: "กำลังประมวลผล",
  READY: "พร้อมใช้งาน",
  FAILED: "ประมวลผลไม่สำเร็จ",
};

export const INDEX_LABELS: Record<IndexStatus, string> = {
  PENDING: "รอสร้างดัชนีค้นหา",
  INDEXING: "กำลังสร้างดัชนีค้นหา",
  READY: "ค้นหาในเนื้อหาได้",
  FAILED: "ค้นหาได้เฉพาะตามคำ",
  SKIPPED: "ไม่มีข้อความให้ค้นหา",
};

export const ACCESS_LABELS: Record<AccessLevel, string> = {
  VIEW: "ดูได้",
  EDIT: "แก้ไขได้",
  MANAGE: "จัดการได้",
};

export const PRINCIPAL_LABELS: Record<PrincipalType, string> = {
  USER: "ผู้ใช้",
  DEPARTMENT: "แผนก",
  ROLE: "บทบาท",
};

export const DOCUMENT_ACTION_LABELS: Record<string, string> = {
  "document.uploaded": "อัปโหลดเอกสาร",
  "document.version_uploaded": "อัปโหลดเวอร์ชันใหม่",
  "document.updated": "แก้ไขข้อมูลเอกสาร",
  "document.deleted": "ลบเอกสาร",
  "document.downloaded": "ดาวน์โหลด",
  "document.acl_changed": "เปลี่ยนสิทธิ์การเข้าถึง",
  "document.reprocess_requested": "สั่งประมวลผลใหม่",
};

export const ACCEPTED_FILES = ".pdf,.docx,.xlsx,.txt";
export const ACCEPTED_EXTENSIONS = ["pdf", "docx", "xlsx", "txt"];
/** Mirrors the backend default UPLOAD_MAX_BYTES (the backend enforces the real limit). */
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Client-side pre-check for a friendlier message; the server sniffs content regardless. */
export function checkFile(file: File): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!ACCEPTED_EXTENSIONS.includes(ext)) return "รองรับเฉพาะไฟล์ PDF, DOCX, XLSX และ TXT";
  if (file.size === 0) return "ไฟล์ว่างเปล่า";
  if (file.size > MAX_UPLOAD_BYTES) return "ไฟล์มีขนาดใหญ่เกิน 25 MB";
  return null;
}
