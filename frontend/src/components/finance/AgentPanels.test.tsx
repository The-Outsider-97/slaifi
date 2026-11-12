import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { AgentStatus, AllocationSuggestion, KnowledgeAnswer, LearningRecall, LearningShare } from "../../types/finance";
import { AgentSwitchRow, AllocationView, KnowledgeResults, LearningMemoryView, agentStateText } from "./AgentPanels";

const agent: AgentStatus = {
  name: "knowledge",
  label: "Knowledge",
  purpose: "Looks things up in SLAIFI's own documentation.",
  enabled: false,
  state: "disabled",
  detail: null,
};

describe("agent switches", () => {
  it("describes an agent that is off as Off, not as a problem", () => {
    expect(agentStateText(agent)).toEqual({ text: "Off", tone: "off" });
  });

  it("says plainly when an agent is on but SLAI could not run it", () => {
    const state = agentStateText({ ...agent, enabled: true, state: "unavailable", detail: "SLAI agent 'knowledge' is not installed." });
    expect(state.tone).toBe("warn");
    expect(state.text).toContain("could not run");
  });

  it("shows an unchecked switch and no Check button while off", () => {
    const html = renderToStaticMarkup(<AgentSwitchRow agent={agent} busy={false} onToggle={() => undefined} onCheck={() => undefined} />);
    expect(html).toContain('role="switch"');
    expect(html).not.toContain("checked");
    expect(html).not.toContain(">Check<");
    expect(html).toContain("Looks things up");
  });

  it("shows the reason when it is on but unavailable, and offers Check", () => {
    const html = renderToStaticMarkup(
      <AgentSwitchRow agent={{ ...agent, enabled: true, state: "unavailable", detail: "scipy is not installed." }} busy={false} onToggle={() => undefined} onCheck={() => undefined} />,
    );
    expect(html).toContain("scipy is not installed.");
    expect(html).toContain(">Check<");
  });
});

describe("knowledge results", () => {
  const answer = (over: Partial<KnowledgeAnswer>): KnowledgeAnswer => ({ status: "ok", detail: null, passages: [], ...over });

  it("lists passages with their source and heading", () => {
    const html = renderToStaticMarkup(
      <KnowledgeResults query="short" answer={answer({ passages: [{ source: "docs/finance/methodology.md", heading: "Short selling", text: "A short position gains when…", score: 1 }] })} />,
    );
    expect(html).toContain("Short selling");
    expect(html).toContain("docs/finance/methodology.md");
    expect(html).toContain("A short position gains when");
  });

  it("is honest when the agent is off, unreachable, or finds nothing", () => {
    expect(renderToStaticMarkup(<KnowledgeResults query="x" answer={answer({ status: "disabled" })} />)).toContain("is off");
    const unavailable = renderToStaticMarkup(<KnowledgeResults query="x" answer={answer({ status: "unavailable", detail: "Not reachable." })} />);
    expect(unavailable).toContain("NOT AVAILABLE");
    expect(unavailable).toContain("Not reachable.");
    expect(renderToStaticMarkup(<KnowledgeResults query="zebra" answer={answer({ status: "no_match" })} />)).toContain("Nothing found");
  });
});

describe("suggested allocation", () => {
  const base: AllocationSuggestion = {
    status: "ok",
    detail: null,
    portfolio_id: "P-1",
    strategy_id: "default",
    focus: "steadiest",
    generated_at: "2026-11-12T10:00:00+00:00",
    solver: "slai-quadratic",
    observations: 250,
    window_start: "2025-11-12",
    window_end: "2026-11-11",
    cash_weight: 0.1,
    current: { annual_volatility: 0.14, historical_annual_return: 0.06 },
    suggested: { annual_volatility: 0.1, historical_annual_return: 0.05 },
    lines: [
      { symbol: "KO", display: "NYSE:KO", current_weight: 0.5, suggested_weight: 0.3, change: -0.2, amount: "-400.00" },
      { symbol: "SPY", display: "NYSE:SPY", current_weight: 0.2, suggested_weight: 0.6, change: 0.4, amount: "800.00" },
    ],
    excluded: [{ symbol: "TSLA", reason: "above the strategy's volatility limit" }],
    checks: [
      { code: "budget", ok: true, message: "ok" },
      { code: "concentration", ok: true, message: "ok" },
    ],
    basis: "Historical statistics from real prices over the window shown. They describe the past and are not a forecast.",
  };

  it("shows current against suggested weights, the checks, what was left out, and that it is not a forecast", () => {
    const html = renderToStaticMarkup(<AllocationView s={base} currency="USD" />);
    expect(html).toContain("NYSE:KO");
    expect(html).toContain("Suggested allocation");
    expect(html).toContain("Adds up to the investable amount");
    expect(html).toContain("TSLA");
    expect(html).toContain("not a forecast");
    expect(html).toContain("no order is placed");
  });

  it("shows nothing as a suggestion when SLAIFI refused the proposal, only why", () => {
    const html = renderToStaticMarkup(
      <AllocationView
        currency="USD"
        s={{ ...base, status: "rejected", lines: [], detail: "SLAIFI did not accept the proposal: Concentration (HHI) 0.250 exceeds the strategy's 0.150.", checks: [{ code: "concentration", ok: false, message: "Concentration (HHI) 0.250 exceeds the strategy's 0.150." }] }}
      />,
    );
    expect(html).toContain("did not accept the proposal");
    expect(html).not.toContain("Suggested allocation");
    expect(html).not.toContain("<table");
  });

  it("says NOT AVAILABLE when the optimizer cannot run, and explains the off state", () => {
    const down = renderToStaticMarkup(<AllocationView currency="USD" s={{ ...base, status: "unavailable", lines: [], observations: 0, detail: "scipy is not installed." }} />);
    expect(down).toContain("NOT AVAILABLE");
    expect(down).toContain("scipy is not installed.");
    const off = renderToStaticMarkup(<AllocationView currency="USD" s={{ ...base, status: "disabled", lines: [], observations: 0 }} />);
    expect(off).toContain("Optimization agent is off");
    expect(off).not.toContain("<table");
  });
});

describe("learning memory", () => {
  const share = (over: Partial<LearningShare>): LearningShare => ({ status: "ok", sent: 0, duplicates: 0, refused: 0, detail: null, ...over });
  const recall = (over: Partial<LearningRecall>): LearningRecall => ({ status: "ok", total: 0, detail: null, by_action: [], ...over });

  it("reports what was sent and what SLAI already held", () => {
    const html = renderToStaticMarkup(<LearningMemoryView share={share({ sent: 3, duplicates: 2, refused: 1 })} recall={null} />);
    expect(html).toContain("3 new, 2 already held, 1 refused by SLAI");
  });

  it("lists what SLAI recorded per recommendation type", () => {
    const html = renderToStaticMarkup(
      <LearningMemoryView share={null} recall={recall({ total: 3, by_action: [{ action: "BUY", count: 3, mean_forward_return: 0.031 }] })} />,
    );
    expect(html).toContain("Outcomes SLAI holds");
    expect(html).toContain(">BUY<");
    expect(html).toContain("3.1%");
  });

  it("is honest when off, unreachable, empty, or nothing has been checked yet", () => {
    expect(renderToStaticMarkup(<LearningMemoryView share={share({ status: "disabled" })} recall={null} />)).toContain("Learning agent is off");
    const down = renderToStaticMarkup(<LearningMemoryView share={null} recall={recall({ status: "unavailable", detail: "No module named 'torch'" })} />);
    expect(down).toContain("NOT AVAILABLE");
    expect(down).toContain("torch");
    expect(renderToStaticMarkup(<LearningMemoryView share={share({ status: "nothing_to_share", detail: "None checked yet." })} recall={null} />)).toContain("Nothing to share yet");
    expect(renderToStaticMarkup(<LearningMemoryView share={null} recall={recall({ status: "empty", detail: "Nothing yet." })} />)).toContain("Nothing recorded yet");
  });
});
