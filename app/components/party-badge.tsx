const colors = {
  D: "bg-blue-100 text-blue-800",
  R: "bg-red-100 text-red-800",
  I: "bg-amber-100 text-amber-800",
} as const;

const labels = { D: "Democrat", R: "Republican", I: "Independent" } as const;

export function PartyBadge({
  party,
  size = "sm",
}: {
  party: "D" | "R" | "I";
  size?: "sm" | "lg";
}) {
  const base = size === "lg" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${base} ${colors[party]}`}>
      {labels[party]}
    </span>
  );
}

export function PartyDot({ party }: { party: "D" | "R" | "I" }) {
  const dot = { D: "bg-blue-500", R: "bg-red-500", I: "bg-amber-500" } as const;
  return <span className={`inline-block h-2 w-2 rounded-full ${dot[party]}`} />;
}
