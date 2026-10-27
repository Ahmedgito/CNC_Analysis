import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AskResult } from "@/lib/api/schemas";
import { AnswerCard } from "./answer-card";

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
  warnings: [],
};

const evidence = {
  cell_id: "mfg_record_A!Parts!C2",
  file: "mfg_record_A.xlsx",
  sheet: "Parts",
  cell: "C2",
  row: 2,
  header: "Material",
  canonical: "material",
  value: "SS304",
  quoted: "SS304",
  hidden: false,
  auto_linked: false,
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
    render(<AnswerCard result={{ ...base, evidence: [evidence] }} onSelectCell={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: /C2/ }));
    expect(onSelect).toHaveBeenCalledWith("mfg_record_A!Parts!C2");
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
