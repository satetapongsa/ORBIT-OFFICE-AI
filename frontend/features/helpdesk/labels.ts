import type { TicketCategory, TicketEventType, TicketStatus } from "@/services/tickets";

/** Same wording as the backend (`app/services/tickets/service.py`), e-mails and the assistant. */
export const TICKET_STATUS_LABELS: Record<TicketStatus, string> = {
  OPEN: "รอรับเรื่อง",
  IN_PROGRESS: "กำลังดำเนินการ",
  WAITING_FOR_USER: "รอข้อมูลจากผู้แจ้ง",
  RESOLVED: "แก้ไขแล้ว",
  CLOSED: "ปิดเรื่อง",
  CANCELLED: "ยกเลิก",
};

export const TICKET_CATEGORY_LABELS: Record<TicketCategory, string> = {
  COMPUTER: "คอมพิวเตอร์",
  NETWORK: "เครือข่าย/อินเทอร์เน็ต",
  PRINTER: "เครื่องพิมพ์",
  SOFTWARE: "โปรแกรม",
  ACCOUNT_ACCESS: "บัญชีและสิทธิ์เข้าใช้",
  OTHER: "อื่นๆ",
};

export const TICKET_EVENT_LABELS: Record<TicketEventType, string> = {
  CREATED: "แจ้งปัญหา",
  STATUS_CHANGED: "เปลี่ยนสถานะ",
  ASSIGNED: "มอบหมายให้",
  UNASSIGNED: "ถอนการมอบหมาย",
  PRIORITY_CHANGED: "เปลี่ยนความสำคัญ",
  CATEGORY_CHANGED: "เปลี่ยนหมวด",
  COMMENTED: "ตอบกลับ",
};

/** Wording for the requester's own status actions (they never see a raw status picker). */
export const REQUESTER_ACTIONS: Partial<Record<TicketStatus, string>> = {
  CANCELLED: "ยกเลิกการแจ้ง",
  CLOSED: "ยืนยันว่าแก้ไขแล้ว",
  OPEN: "ยังไม่หาย เปิดเรื่องอีกครั้ง",
};

export const OPEN_TICKET_STATUSES: TicketStatus[] = ["OPEN", "IN_PROGRESS", "WAITING_FOR_USER"];
