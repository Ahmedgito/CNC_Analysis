import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AskResult, Evidence } from "@/lib/api/schemas";
import { AnswerCard, previewSources } from "./answer-card";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const base: AskResult = {
  part_number: "2280",
  question: "q",
  status: "answered",
  answer: "Material: SS304.",
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

const evidence: Evidence = {
  fact_id: "mfg_record_A!Parts!C2",
  source: "excel",
  file: "mfg_record_A.xlsx",
  locator: "Parts › C2",
  sheet: "Parts",
  cell: "C2",
  row: 2,
  header: "Material",
  canonical: "material",
  value: "SS304",
  quoted: "SS304",
  hidden: false,
  stale: false,
  confidence: "exact",
  auto_linked: false,
};

const drawingEvidence: Evidence = {
  fact_id: "2283_bushing!p1!dim!2",
  source: "pdf",
  file: "2283_bushing.pdf",
  locator: "p1 › Dimension › Diameter",
  header: "Diameter",
  canonical: null,
  value: "Ø48",
  quoted: "Ø48",
  hidden: false,
  stale: false,
  confidence: "exact",
  auto_linked: false,
  page: 1,
  region: "dimension",
  bbox: [218.2, 321.1, 235.3, 330.1],
};

describe("AnswerCard", () => {
  it("shows the answer, status and a source chip naming file, sheet and cell", () => {
    render(<AnswerCard result={{ ...base, evidence: [evidence] }} />);
    expect(screen.getByText("Answered from the files")).toBeInTheDocument();
    expect(screen.getByText("Material: SS304.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mfg_record_A\.xlsx › Parts › C2/ })).toBeInTheDocument();
  });

  it("selects the cited cell when a chip is clicked", async () => {
    const onSelect = vi.fn();
    render(<AnswerCard result={{ ...base, evidence: [evidence] }} onSelectFact={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: /C2/ }));
    expect(onSelect).toHaveBeenCalledWith("mfg_record_A!Parts!C2");
  });

  it("names the drawing file, page and callout for a PDF source", async () => {
    const onSelect = vi.fn();
    render(
      <AnswerCard result={{ ...base, evidence: [evidence, drawingEvidence] }} onSelectFact={onSelect} />,
    );
    const chip = screen.getByRole("button", { name: /2283_bushing\.pdf › p1 › Dimension › Diameter/ });
    expect(chip).toHaveTextContent("Ø48");
    await userEvent.click(chip);
    expect(onSelect).toHaveBeenCalledWith("2283_bushing!p1!dim!2");
  });

  it("shows a few sources and a See all button for the rest", async () => {
    const many = Array.from({ length: 7 }, (_, i) => ({
      ...evidence,
      fact_id: `mfg_record_A!Parts!C${i + 2}`,
      locator: `Parts › C${i + 2}`,
      cell: `C${i + 2}`,
    }));
    render(<AnswerCard result={{ ...base, evidence: many }} />);
    expect(screen.getAllByRole("button", { name: /mfg_record_A\.xlsx › Parts/ })).toHaveLength(4);
    const toggle = screen.getByRole("button", { name: /See all 7 sources/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(await screen.findAllByRole("button", { name: /mfg_record_A\.xlsx › Parts/ })).toHaveLength(7);
    await userEvent.click(screen.getByRole("button", { name: /Show fewer/ }));
    expect(screen.getByRole("button", { name: /See all 7 sources/ })).toBeInTheDocument();
  });

  it("does not offer See all when every source fits", () => {
    render(<AnswerCard result={{ ...base, evidence: [evidence, drawingEvidence] }} />);
    expect(screen.queryByRole("button", { name: /See all/ })).not.toBeInTheDocument();
  });

  it("keeps a drawing source in the preview when the spreadsheet cites more", () => {
    const cells = Array.from({ length: 5 }, (_, i) => ({ ...evidence, fact_id: `x!Parts!C${i}` }));
    const preview = previewSources([...cells, drawingEvidence]);
    expect(preview).toHaveLength(4);
    expect(preview.map((e) => e.source)).toContain("pdf");
    expect(preview.at(-1)?.fact_id).toBe(drawingEvidence.fact_id); // answer order kept
  });

  it("opens the full list when the highlighted source is one of the hidden ones", () => {
    const many = Array.from({ length: 6 }, (_, i) => ({ ...evidence, fact_id: `x!Parts!C${i}` }));
    render(<AnswerCard result={{ ...base, evidence: many }} selectedFactId="x!Parts!C5" />);
    expect(screen.getAllByRole("button", { name: /mfg_record_A\.xlsx/ })).toHaveLength(6);
  });

  it("labels values read from a scan by the vision model", () => {
    render(<AnswerCard result={{ ...base, evidence: [{ ...drawingEvidence, confidence: "vision" }] }} />);
    expect(screen.getByLabelText("read by vision model")).toBeInTheDocument();
  });

  it("asks before reading a scanned drawing and sends the approval reply", async () => {
    const onAction = vi.fn();
    const action = {
      id: "read_scan" as const,
      file: "3001_gear_blank_scan.pdf",
      label: "Read 3001_gear_blank_scan.pdf with the vision model",
      reply: "Yes, read the scanned drawing.",
    };
    render(
      <AnswerCard
        result={{
          ...base,
          status: "needs_consent",
          answer: "The drawing is a scanned image that the app has not read.",
          confidence: "low",
          actions: [action],
        }}
        onAction={onAction}
      />,
    );
    expect(screen.getByText("Needs your go-ahead")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: action.label });
    await userEvent.click(button);
    expect(onAction).toHaveBeenCalledWith(action);
    expect(screen.getByRole("button", { name: "Reading the scan…" })).toBeDisabled();
  });

  it("does not offer the action while another question is running", () => {
    render(
      <AnswerCard
        result={{
          ...base,
          actions: [{ id: "read_scan", file: "a.pdf", label: "Read a.pdf", reply: "Yes" }],
        }}
      />,
    );
    expect(screen.getByRole("button", { name: "Read a.pdf" })).toBeDisabled();
  });

  it("shows spreadsheet and drawing values side by side, disagreements first", () => {
    render(
      <AnswerCard
        result={{
          ...base,
          cross_checks: [
            {
              field: "bore",
              label: "Bore",
              verdict: "agree",
              excel: ["job_cards_B!Job Cards!E5"],
              pdf: ["2283_bushing!p1!dim!3"],
              excel_value: "Ø30",
              pdf_value: "Ø30",
              detail: "Both say Ø30.",
            },
            {
              field: "outer_diameter",
              label: "Outer diameter",
              verdict: "disagree",
              excel: ["job_cards_B!Job Cards!E5"],
              pdf: ["2283_bushing!p1!dim!2"],
              excel_value: "Ø50",
              pdf_value: "Ø48",
              detail: "Different diameters.",
            },
          ],
        }}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Outer diameter");
    expect(items[0]).toHaveTextContent("Disagree");
    expect(items[0]).toHaveTextContent("Ø50");
    expect(items[0]).toHaveTextContent("Ø48");
    expect(items[1]).toHaveTextContent("Agree");
  });

  it("renders not-found answers with what the record does contain", () => {
    render(
      <AnswerCard
        result={{
          ...base,
          status: "not_found",
          answer: "I can't find that in the provided files.",
          available_fields: ["material grade", "raw stock size"],
          confidence: "low",
        }}
      />,
    );
    expect(screen.getByText("Not in the files")).toBeInTheDocument();
    expect(screen.getByText("material grade · raw stock size")).toBeInTheDocument();
    expect(screen.queryByText(/citations verified/)).not.toBeInTheDocument();
  });

  it("shows the computation working and labels it as app-computed", () => {
    render(
      <AnswerCard
        result={{
          ...base,
          status: "computed",
          answer: "Total setup is 12 min.",
          computation: {
            label: "total setup time",
            expression: "c1 + c2 + c3",
            working: "5 + 3 + 4 = 12 min",
            result: 12,
            display: "12 min",
            unit: "min",
            inputs: [],
            constants: [],
          },
        }}
      />,
    );
    expect(screen.getByText("5 + 3 + 4 = 12 min")).toBeInTheDocument();
    expect(screen.getByText(/not by the language model/)).toBeInTheDocument();
  });

  it("keeps general knowledge visibly separate from file facts", () => {
    render(
      <AnswerCard result={{ ...base, general_knowledge: ["ISO 2768-m is a medium tolerance class."] }} />,
    );
    expect(screen.getByText(/general knowledge, not from the files/i)).toBeInTheDocument();
  });

  it("flags a fallback provider in the footer", () => {
    render(
      <AnswerCard
        result={{
          ...base,
          provider: {
            provider: "groq",
            model: "openai/gpt-oss-120b",
            fallback_used: true,
            fallback_reason: "anthropic: 529 overloaded",
            refusal_fallback_used: false,
            attempts: 3,
            latency_ms: 2400,
          },
        }}
      />,
    );
    expect(screen.getByText("fallback provider")).toBeInTheDocument();
    expect(screen.getByText(/openai\/gpt-oss-120b · 2\.4 s/)).toBeInTheDocument();
  });
});
