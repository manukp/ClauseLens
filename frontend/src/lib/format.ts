// Small presentation helpers. Sentence case + restraint per the design tokens.

export function fmtCost(usd: number): string {
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  if (usd >= 0.01) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(4)}`;
}

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return `${n}`;
}

export function fmtLatency(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.round(ms)} ms`;
}

export function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function fmtClock(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtElapsed(fromTs: number | null | undefined, toTs?: number): string {
  if (!fromTs) return "—";
  const end = toTs ?? Date.now() / 1000;
  return fmtDuration(Math.max(0, end - fromTs));
}

// Tier label + the mockup's two tier hues (haiku teal, sonnet violet).
export function tierMeta(tier: string): { label: string; color: string; key: "h" | "s" | "t" } {
  const t = tier.toLowerCase();
  if (t === "sonnet") return { label: "Sonnet 4.6", color: "#8E84C8", key: "s" };
  if (t === "haiku") return { label: "Haiku 4.5", color: "#6FA8B8", key: "h" };
  if (t === "titan") return { label: "Titan embed", color: "#4D7C6F", key: "t" };
  return { label: tier, color: "#6B7686", key: "h" };
}
