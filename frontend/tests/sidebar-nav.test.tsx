import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SidebarNav } from "@/components/layout/sidebar-nav";
import { MAIN_NAV, isNavItemActive } from "@/lib/navigation";

vi.mock("next/navigation", () => ({ usePathname: () => "/dashboard" }));

let permissions = new Set<string>();
vi.mock("@/features/auth/hooks/use-session", () => ({
  useSession: () => ({ has: (p: string) => permissions.has(p) }),
}));

const ALL = MAIN_NAV.map((i) => i.permission).filter((p): p is string => p !== null);

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

  it("does not render links for modules that are not implemented yet", () => {
    render(<SidebarNav />);
    const assistant = screen.getByTestId("nav-assistant"); // Phase 6
    expect(assistant.tagName).not.toBe("A");
    expect(assistant).toHaveAttribute("aria-disabled", "true");
    expect(assistant).toHaveTextContent("เร็วๆ นี้");
    for (const key of ["dashboard", "notifications", "system-status"]) {
      expect(screen.getByTestId(`nav-${key}`).tagName).toBe("A");
    }
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
