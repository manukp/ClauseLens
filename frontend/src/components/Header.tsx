import { useEffect, useState } from "react";

// Top header. Shows a small live indicator that pings /api/health so the demo
// operator can see the process is up at a glance.
export default function Header() {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/health")
      .then((r) => r.ok)
      .then((v) => active && setOk(v))
      .catch(() => active && setOk(false));
    return () => {
      active = false;
    };
  }, []);

  const dot =
    ok === null ? "bg-slate/40" : ok ? "bg-severity-low" : "bg-severity-high";

  return (
    <header className="flex items-center justify-between border-b border-ink/10 bg-canvas px-8 py-4">
      <h1 className="text-sm font-medium text-slate">
        Contract analysis workspace
      </h1>
      <div className="flex items-center gap-2 text-xs text-slate">
        <span className={`inline-block h-2 w-2 rounded-full ${dot}`} />
        {ok === null ? "checking…" : ok ? "service online" : "service offline"}
      </div>
    </header>
  );
}
