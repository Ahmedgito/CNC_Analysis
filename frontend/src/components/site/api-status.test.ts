import { describe, expect, it } from "vitest";
import { describeEngines } from "./api-status";

describe("describeEngines", () => {
  it("lists every configured engine, including Claude Code", () => {
    expect(describeEngines({ anthropic_key: false, claude_code_token: true, groq_key: true })).toBe(
      "Claude Code + Groq",
    );
  });

  it("falls back to the offline rules engine when nothing is configured", () => {
    expect(describeEngines({ anthropic_key: false, groq_key: false })).toBe("offline rules engine");
    expect(describeEngines({})).toBe("offline rules engine");
  });

  it("humanises providers the backend adds later", () => {
    expect(describeEngines({ openai_api_key: true })).toBe("Openai Api");
  });
});
