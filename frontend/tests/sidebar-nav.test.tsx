import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SidebarNav } from "@/components/layout/sidebar-nav";
import {
  CURRENT_PHASE,
  MAIN_NAV,
  SECONDARY_NAV,
  isNavItemActive,
  isNavItemAvailable,
} from "@/lib/navigation";

vi.mock("next/navigation", () => ({ usePathname: () => "/dashboard" }));

let permissions = new Set<string>();
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ has: (p: string) => permissions.has(p) }),
}));

const ALL = [...MAIN_NAV, ...SECONDARY_NAV]
  .map((i) => i.permission)
  .filter((p): p is string => p !== null);

describe("SidebarNav", () => {
  beforeEach(() => {
    permissions = new Set(ALL);
  });

  it("renders every permitted module with its Thai label", () => {
    render(<SidebarNav />);
    for (const item of MAIN_NAV) {
      expect(screen.getByTestId(`nav-${item.key}`)).toHaveTextContent(item.label);
    }
  });

  it("hides modules the user has no permission for", () => {
    permissions = new Set(["documents:read"]);
    render(<SidebarNav />);
    expect(screen.getByTestId("nav-documents")).toBeInTheDocument();
    expect(screen.getByTestId("nav-dashboard")).toBeInTheDocument(); // no permission required
    expect(screen.queryByTestId("nav-assistant")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-employees")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-settings")).not.toBeInTheDocument();
  });

  it("links every module once its phase has shipped (Phase 8: all of them)", () => {
    render(<SidebarNav />);
    for (const item of [...MAIN_NAV, ...SECONDARY_NAV]) {
      const link = screen.getByTestId(`nav-${item.key}`);
      expect(link.tagName).toBe("A");
      expect(link).toHaveAttribute("href", item.href);
    }
    expect(screen.queryByText("เร็วๆ นี้")).not.toBeInTheDocument();
  });

  it("treats modules of later phases as unavailable", () => {
    const helpdesk = MAIN_NAV.find((i) => i.key === "helpdesk");
    expect(helpdesk).toBeDefined();
    if (!helpdesk) return;
    expect(CURRENT_PHASE).toBe(8);
    expect(isNavItemAvailable(helpdesk)).toBe(true);
    expect(isNavItemAvailable(helpdesk, 7)).toBe(false);
  });

  it("marks the current page as active", () => {
    render(<SidebarNav />);
    expect(screen.getByTestId("nav-dashboard")).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("nav-system-status")).not.toHaveAttribute("aria-current");
  });
});

describe("isNavItemActive", () => {
  it("matches nested routes but not other paths that share a prefix", () => {
    const docs = MAIN_NAV.find((i) => i.key === "documents");
    expect(docs).toBeDefined();
    if (!docs) return;
    expect(isNavItemActive(docs, "/documents/123")).toBe(true);
    expect(isNavItemActive(docs, "/documents-archive")).toBe(false);
  });
});
