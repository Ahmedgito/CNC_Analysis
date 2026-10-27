import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AskResult, CrossCheck, Evidence } from "@/lib/api/schemas";
import { counterparts, FactSelectionProvider } from "@/lib/selection";
import { AnswerCard } from "./answer-card";
import { CrossCheckList } from "./cross-checks";
import { sanitizeSvg } from "./model/model-projections";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

const od: CrossCheck = {
  field: "outer_diameter",
  label: "Outer diameter",
  verdict: "disagree",
  excel: ["job_cards_B!Job Cards!E5"],
  pdf: ["2283_bushing!p1!dim!2"],
  iges: ["2283_bushing!m!od_1"],
  excel_value: "Ø50 x 40, bore Ø30",
  pdf_value: "Ø48",
  iges_value: "Ø48 × 40 long",
  sides: [
    {
      source: "excel",
      facts: ["job_cards_B!Job Cards!E5"],
      value: "Ø50 x 40, bore Ø30",
      normalised: "50 mm",
    },
    { source: "pdf", facts: ["2283_bushing!p1!dim!2"], value: "Ø48", normalised: "48 mm" },
    { source: "iges", facts: ["2283_bushing!m!od_1"], value: "Ø48 × 40 long", normalised: "48 mm" },
  ],
  pairs: { "excel~pdf": "disagree", "pdf~iges": "agree", "excel~iges": "disagree" },
  odd_one_out: "excel",
  dissent: ["job_cards_B!Job Cards!E5"],
  detail: "The drawing and the model agree on 48 mm; Job Cards › E5 says 50 mm.",
};
const material: CrossCheck = {
  field: "material",
  label: "Material",
  verdict: "agree",
  excel: ["a!Parts!C2"],
  pdf: ["a!p1!tb!material"],
  iges: [],
  excel_value: "SS304",
  pdf_value: "SS304 (AISI 304)",
  sides: [
    { source: "excel", facts: ["a!Parts!C2"], value: "SS304" },
    { source: "pdf", facts: ["a!p1!tb!material"], value: "SS304 (AISI 304)" },
    { source: "iges", facts: [], note: "a 3D model does not record the material" },
  ],
  pairs: { "excel~pdf": "agree" },
  dissent: [],
  detail: "The same material.",
};

describe("linked selection", () => {
  it("finds the same field in the other files", () => {
    expect(counterparts([material, od], "2283_bushing!m!od_1")).toEqual({
      field: "outer_diameter",
      label: "Outer diameter",
      ids: ["job_cards_B!Job Cards!E5", "2283_bushing!p1!dim!2"],
    });
    expect(counterparts([od], "unrelated!m!volume")).toBeNull();
  });
});

describe("three-way cross-check", () => {
  it("shows three files, the pairwise verdicts and the odd one out", () => {
    render(<CrossCheckList checks={[material, od]} />);
    const item = screen.getByText("Outer diameter").closest("li")!;
    expect(within(item).getByText("odd one out")).toBeInTheDocument();
    expect(within(item).getByText("3D model")).toBeInTheDocument();
    expect(within(item).getByRole("list", { name: "Pairwise verdicts" })).toHaveTextContent(
      "Drawing ↔ Model",
    );
    // Disagreements sort first.
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("Outer diameter");
  });

  it("says the model holds no material instead of leaving a gap", () => {
    render(<CrossCheckList checks={[material]} />);
    expect(screen.getByText("does not state")).toBeInTheDocument();
    expect(screen.getByText("a 3D model does not record the material")).toBeInTheDocument();
  });

  it("filters by verdict", async () => {
    render(<CrossCheckList checks={[material, od]} filterable />);
    await userEvent.click(screen.getByRole("button", { name: /Disagree 1/ }));
    expect(screen.queryByText("Material")).not.toBeInTheDocument();
    expect(screen.getByText("Outer diameter")).toBeInTheDocument();
  });

  it("outlines counterparts of the selected fact", () => {
    render(
      <FactSelectionProvider primary="2283_bushing!m!od_1" checks={[od]}>
        <CrossCheckList checks={[od]} onSelect={() => {}} />
      </FactSelectionProvider>,
    );
    const model = screen.getByRole("button", { name: /3D model/i });
    expect(model.className).toContain("border-amber-400");
    const drawing = screen.getByRole("button", { name: /^Drawing/i });
    expect(drawing.className).toContain("border-dashed");
  });
});

const base: AskResult = {
  part_number: "2283",
  question: "q",
  status: "answered",
  answer: "Ø48 on the drawing and the model; Ø50 in the job card.",
  evidence: [],
  general_knowledge: [],
  missing_information: [],
  available_fields: [],
  suggestions: [],
  confidence: "high",
  sources: {},
  cross_checks: [],
  actions: [],
  warnings: [],
};
const modelEvidence: Evidence = {
  fact_id: "2283_bushing!m!od_1",
  source: "iges",
  file: "2283_bushing.igs",
  locator: "Model › Outer diameter",
  header: "Outer diameter",
  canonical: "outer_diameter",
  value: "Ø48 × 40 long",
  quoted: "Ø48 × 40 long",
  hidden: false,
  stale: false,
  confidence: "measured",
  auto_linked: false,
  feature: "od_1",
  method: "outer cylinder on the turning axis",
};
const cellEvidence: Evidence = {
  ...modelEvidence,
  fact_id: "job_cards_B!Job Cards!E5",
  source: "excel",
  file: "job_cards_B.xlsx",
  locator: "Job Cards › E5",
  header: "Final Dims",
  value: "Ø50 x 40, bore Ø30",
  quoted: "Ø50 x 40, bore Ø30",
  confidence: "exact",
  feature: null,
};

describe("model evidence", () => {
  it("names the model file and feature and selects it", async () => {
    const onSelect = vi.fn();
    render(
      <AnswerCard result={{ ...base, evidence: [cellEvidence, modelEvidence] }} onSelectFact={onSelect} />,
    );
    const chip = screen.getByRole("button", { name: /2283_bushing\.igs › Model › Outer diameter/ });
    await userEvent.click(chip);
    expect(onSelect).toHaveBeenCalledWith("2283_bushing!m!od_1");
    expect(screen.getByText(/1 spreadsheet, 1 model/)).toBeInTheDocument();
  });
});

describe("projection sanitiser", () => {
  it("keeps drawing elements and fact ids, drops anything active", () => {
    const svg =
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" onload="alert(1)">' +
      "<script>alert(1)</script><foreignObject><div>x</div></foreignObject>" +
      '<a href="javascript:alert(1)"><path d="M0 0"/></a>' +
      '<g class="features"><circle data-fact-id="a!m!bore" cx="1" cy="1" r="1" onclick="x()"/></g></svg>';
    const out = sanitizeSvg(svg)!;
    expect(out).not.toMatch(/script|foreignObject|onload|onclick|javascript/);
    expect(out).toContain('data-fact-id="a!m!bore"');
    expect(sanitizeSvg("<html><body>not svg</body></html>")).toBeNull();
  });
});
