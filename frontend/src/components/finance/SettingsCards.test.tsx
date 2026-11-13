import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ProviderKeyInfo } from "../../types/finance";
import { PlatformFeesCard, ProviderKeyEditor } from "./SettingsCards";

const none: ProviderKeyInfo = { name: "tiingo", label: "Tiingo", env_var: "SLAIFI_TIINGO_API_KEY", configured: false, source: null };

function html(info: ProviderKeyInfo): string {
  return renderToStaticMarkup(<ProviderKeyEditor info={info} onChanged={() => undefined} />);
}

describe("provider key editor", () => {
  it("offers a password box and says there is no key yet", () => {
    const out = html(none);
    expect(out).toContain('type="password"');
    expect(out).toContain('autoComplete="off"');
    expect(out).toContain("No key yet");
    expect(out).toContain("Save key");
    expect(out).not.toContain(">Remove<");
    expect(out).not.toContain(">Test<");
  });

  it("says a key from .env is from .env and cannot be removed here", () => {
    const out = html({ ...none, configured: true, source: "environment" });
    expect(out).toContain("From the .env file or environment");
    expect(out).toContain(">Test<");
    expect(out).not.toContain(">Remove<");
  });

  it("offers Remove only for a key saved in SLAIFI, and never puts a key in the page", () => {
    const out = html({ ...none, configured: true, source: "settings" });
    expect(out).toContain("Saved in SLAIFI");
    expect(out).toContain(">Remove<");
    expect(/value="[^"]+"/.test(out)).toBe(false);
  });
});

describe("platform costs card", () => {
  it("explains what the fees are while the saved values load", () => {
    const out = renderToStaticMarkup(<PlatformFeesCard />);
    expect(out).toContain("Trading platform costs");
    expect(out).toContain("withdrawal fee");
    expect(out).toContain("Enter 0 if your platform charges nothing");
  });
});
