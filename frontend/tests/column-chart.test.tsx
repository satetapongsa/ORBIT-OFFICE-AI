import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ColumnChart, niceMax } from "@/components/charts/column-chart";

const series = [
  { key: "ok", label: "สำเร็จ", color: "var(--chart-1)" },
  { key: "fail", label: "ไม่สำเร็จ", color: "var(--chart-2)" },
];
const data = [
  { key: "2026-11-10", label: "10", fullLabel: "10 พ.ย. 2569", values: { ok: 5, fail: 1 } },
  { key: "2026-11-11", label: "11", fullLabel: "11 พ.ย. 2569", values: { ok: 2, fail: 0 } },
];

describe("niceMax", () => {
  it("rounds up to an even ceiling so every gridline is a whole number", () => {
    expect(niceMax(0)).toBe(4);
    expect(niceMax(3)).toBe(4);
    expect(niceMax(7)).toBe(8);
    expect(niceMax(13)).toBe(20);
    expect(niceMax(21)).toBe(30);
    expect(niceMax(250)).toBe(250);
    expect(niceMax(480)).toBe(500);
  });
});

describe("ColumnChart", () => {
  it("describes each column for assistive technology and shows a tooltip on focus", () => {
    render(<ColumnChart title="ทดสอบ" data={data} series={series} unit="ครั้ง" />);
    const column = screen.getByTestId("column-2026-11-10");
    expect(column).toHaveAccessibleName("10 พ.ย. 2569: สำเร็จ 5 ครั้ง, ไม่สำเร็จ 1 ครั้ง");
    fireEvent.focus(column);
    expect(screen.getByRole("tooltip")).toHaveTextContent("10 พ.ย. 2569");
    expect(screen.getByRole("tooltip")).toHaveTextContent("5 ครั้ง");
    fireEvent.blur(column);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("shows a legend only for multiple series", () => {
    const { rerender } = render(<ColumnChart title="t" data={data} series={series} />);
    expect(screen.getByLabelText("คำอธิบายสัญลักษณ์")).toBeInTheDocument();
    rerender(<ColumnChart title="t" data={data} series={series.slice(0, 1)} />);
    expect(screen.queryByLabelText("คำอธิบายสัญลักษณ์")).not.toBeInTheDocument();
  });

  it("offers the same data as a table", async () => {
    render(<ColumnChart title="ตารางทดสอบ" data={data} series={series} />);
    await userEvent.click(screen.getByRole("button", { name: "ดูเป็นตาราง" }));
    const table = screen.getByRole("table", { name: "ตารางทดสอบ" });
    expect(table).toHaveTextContent("11 พ.ย. 2569");
    expect(screen.getAllByRole("row")).toHaveLength(3);
    await userEvent.click(screen.getByRole("button", { name: "ดูเป็นกราฟ" }));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
