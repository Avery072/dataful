import type { Health, Role, Severity } from "../api";

const HEALTH_LABEL: Record<Health, string> = { healthy: "Healthy", gaps: "Has gaps", trap: "Possible trap" };

/** Health marker: shape + color, never color alone. */
export function HealthMark({ health, size = 11 }: { health: Health; size?: number }) {
  const s = size;
  return (
    <svg className={`health health-${health}`} width={s} height={s} viewBox="0 0 12 12" role="img" aria-label={HEALTH_LABEL[health]}>
      <title>{HEALTH_LABEL[health]}</title>
      {health === "healthy" && <circle cx="6" cy="6" r="4.5" fill="currentColor" />}
      {health === "gaps" && (
        <>
          <circle cx="6" cy="6" r="4.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M6 1.75 A4.25 4.25 0 0 1 6 10.25 Z" fill="currentColor" />
        </>
      )}
      {health === "trap" && <path d="M6 1.2 L11 10.5 H1 Z" fill="currentColor" strokeLinejoin="round" />}
    </svg>
  );
}

export const SEVERITY_HEALTH: Record<Severity, Health | "format"> = { numbers: "trap", missing: "gaps", format: "format" };

/** Marker for an issue severity: ▲ numbers, ◐ missing, ◆ formatting. */
export function SeverityMark({ severity }: { severity: Severity }) {
  if (severity === "format") {
    return (
      <svg className="health health-format" width="11" height="11" viewBox="0 0 12 12" role="img" aria-label="Formatting">
        <rect x="2.5" y="2.5" width="7" height="7" transform="rotate(45 6 6)" fill="currentColor" />
      </svg>
    );
  }
  return <HealthMark health={severity === "numbers" ? "trap" : "gaps"} />;
}

const ROLE_GLYPH: Record<Role, { g: string; label: string; plain: string }> = {
  measure: { g: "∑", label: "Number", plain: "A number you can add up or average" },
  category: { g: "◇", label: "Category", plain: "A label that repeats — good for grouping" },
  identifier: { g: "#", label: "ID", plain: "Names one record — don't add these up" },
  time: { g: "◷", label: "Date / time", plain: "A date or time" },
  text: { g: "¶", label: "Text", plain: "Free text, mostly unique" },
  geo: { g: "⌖", label: "Place", plain: "A country, city or other place" },
  boolean: { g: "◑", label: "Yes / no", plain: "Only two values, like yes or no" },
};

export function RoleGlyph({ role }: { role: Role }) {
  const r = ROLE_GLYPH[role] ?? ROLE_GLYPH.text;
  return (
    <span className="role-glyph" title={`${r.label}: ${r.plain.toLowerCase()}`} aria-label={r.label} role="img">
      {r.g}
    </span>
  );
}
export const roleLabel = (r: Role) => (ROLE_GLYPH[r] ?? ROLE_GLYPH.text).label;
export const rolePlain = (r: Role) => (ROLE_GLYPH[r] ?? ROLE_GLYPH.text).plain;

/** Small key to the column-type symbols, highlighting the current one. */
export function RoleLegend({ current }: { current?: Role }) {
  return (
    <ul className="role-legend">
      {(Object.keys(ROLE_GLYPH) as Role[]).map((r) => (
        <li key={r} className={r === current ? "on" : ""}>
          <span className="role-glyph" aria-hidden>
            {ROLE_GLYPH[r].g}
          </span>
          <span>
            <b>{ROLE_GLYPH[r].label}</b> — {ROLE_GLYPH[r].plain.toLowerCase()}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Icon({ name, size = 14 }: { name: "search" | "close" | "sort-asc" | "sort-desc" | "sort" | "download" | "sun" | "moon" | "plus" | "sparkle" | "group" | "notes" | "file" | "sheet" | "collapse" | "expand"; size?: number }) {
  const p = { width: size, height: size, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  switch (name) {
    case "search": return <svg {...p}><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5 14 14" /></svg>;
    case "close": return <svg {...p}><path d="M4 4l8 8M12 4l-8 8" /></svg>;
    case "sort-asc": return <svg {...p}><path d="M8 13V3M4 7l4-4 4 4" /></svg>;
    case "sort-desc": return <svg {...p}><path d="M8 3v10M4 9l4 4 4-4" /></svg>;
    case "sort": return <svg {...p}><path d="M5 6l3-3 3 3M5 10l3 3 3-3" /></svg>;
    case "download": return <svg {...p}><path d="M8 2v8M4.5 6.5 8 10l3.5-3.5M3 13.5h10" /></svg>;
    case "sun": return <svg {...p}><circle cx="8" cy="8" r="3" /><path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" /></svg>;
    case "moon": return <svg {...p}><path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z" /></svg>;
    case "plus": return <svg {...p}><path d="M8 3v10M3 8h10" /></svg>;
    case "sparkle": return <svg {...p}><path d="M8 2c.4 2.8 1.2 3.6 4 4-2.8.4-3.6 1.2-4 4-.4-2.8-1.2-3.6-4-4 2.8-.4 3.6-1.2 4-4zM12.5 10.5c.2 1.2.6 1.6 1.8 1.8-1.2.2-1.6.6-1.8 1.8-.2-1.2-.6-1.6-1.8-1.8 1.2-.2 1.6-.6 1.8-1.8z" /></svg>;
    case "group": return <svg {...p}><path d="M2.5 4h11M2.5 8h7M2.5 12h4" /></svg>;
    case "notes": return <svg {...p}><path d="M3 2.5h10v11H3zM5.5 6h5M5.5 8.5h5M5.5 11h3" /></svg>;
    case "file": return <svg {...p}><path d="M4 1.5h5l3 3v10H4z M9 1.5v3h3" /></svg>;
    case "collapse": return <svg {...p}><path d="M6 4l4 4-4 4M12.5 2.5v11" /></svg>;
    case "expand": return <svg {...p}><path d="M10 4L6 8l4 4M3.5 2.5v11" /></svg>;
    case "sheet": return <svg {...p}><path d="M2.5 3h11v10h-11zM2.5 6.5h11M6.5 3v10" /></svg>;
  }
}
