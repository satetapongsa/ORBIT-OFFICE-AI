import type { ComponentStatus } from "@/services/health";

export const COMPONENT_LABELS: Record<string, { title: string; description: string }> = {
  database: { title: "ฐานข้อมูล", description: "PostgreSQL พร้อมส่วนขยาย pgvector" },
  redis: { title: "Redis", description: "คิวงานเบื้องหลังและแคช" },
  object_storage: { title: "ที่เก็บไฟล์", description: "MinIO / S3 สำหรับไฟล์เอกสาร" },
  ai_chat: { title: "AI โมเดลสนทนา", description: "ผู้ให้บริการโมเดลภาษาสำหรับผู้ช่วย AI" },
  ai_embedding: { title: "AI โมเดลเวกเตอร์", description: "โมเดล Embedding สำหรับค้นหาเอกสาร" },
};

export const STATUS_LABELS: Record<ComponentStatus, string> = {
  ok: "ปกติ",
  error: "ขัดข้อง",
  configured: "ตั้งค่าแล้ว",
  not_configured: "ยังไม่ได้ตั้งค่า",
};

/** Thai text for the generic detail codes the backend returns; other details are technical. */
const DETAIL_LABELS: Record<string, string> = {
  unavailable: "ไม่สามารถเชื่อมต่อได้",
  "timed out": "หมดเวลารอการตอบกลับ",
};

export function componentLabel(name: string) {
  return COMPONENT_LABELS[name] ?? { title: name, description: "" };
}

export function detailLabel(detail: string): { text: string; technical: boolean } {
  const translated = DETAIL_LABELS[detail];
  return translated ? { text: translated, technical: false } : { text: detail, technical: true };
}
