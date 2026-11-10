import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SidebarNav } from "@/components/layout/sidebar-nav";
import { MAIN_NAV, isNavItemActive } from "@/lib/navigation";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

describe("SidebarNav", () => {
  it("renders every module with its Thai label", () => {
    render(<SidebarNav />);
    for (const item of MAIN_NAV) {
      expect(screen.getByTestId(`nav-${item.key}`)).toHaveTextContent(item.label);
    }
  });

  it("does not render links for modules that are not implemented yet", () => {
    render(<SidebarNav />);
    const dashboard = screen.getByTestId("nav-dashboard");
    expect(dashboard.tagName).not.toBe("A");
    expect(dashboard).toHaveAttribute("aria-disabled", "true");
  });

  it("marks the current page as active", () => {
    render(<SidebarNav />);
    const status = screen.getByTestId("nav-system-status");
    expect(status.tagName).toBe("A");
    expect(status).toHaveAttribute("aria-current", "page");
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
