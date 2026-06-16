import { NavLink } from "react-router-dom";

// Navy nav rail (Ink). Wordmark in Spectral; everything else Inter.
const NAV = [
  { to: "/new", label: "New analysis" },
  { to: "/analysis", label: "View analysis" },
  { to: "/admin", label: "Admin" },
];

export default function NavRail() {
  return (
    <nav className="flex w-60 shrink-0 flex-col bg-ink text-canvas shadow-rail">
      <div className="px-6 py-6">
        <span className="font-wordmark text-2xl font-semibold tracking-tight text-canvas">
          Clause<span className="text-marigold">Lens</span>
        </span>
        <p className="mt-1 text-xs text-canvas/50">Contract clause analyzer</p>
      </div>

      <ul className="mt-2 flex flex-col gap-1 px-3">
        {NAV.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                [
                  "block rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-canvas/10 text-canvas font-medium"
                    : "text-canvas/60 hover:bg-canvas/5 hover:text-canvas",
                ].join(" ")
              }
            >
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="mt-auto px-6 py-5 text-[11px] leading-relaxed text-canvas/35">
        Proof of concept · every output traceable to a cited source clause.
      </div>
    </nav>
  );
}
