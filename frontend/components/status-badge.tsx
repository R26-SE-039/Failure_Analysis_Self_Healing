type StatusBadgeProps = {
  label: string;
  type?: "status" | "healing" | "risk" | "rootCause";
};

export default function StatusBadge({
  label,
  type = "status",
}: StatusBadgeProps) {
  const value = label.toLowerCase();

  let classes =
    "inline-flex rounded-full px-3 py-1 text-xs font-medium border";

  if (type === "status") {
    if (value === "fail") {
      classes += " bg-red-500/10 text-red-600 border-red-500/20";
    } else if (value === "pass") {
      classes += " bg-green-500/10 text-green-600 border-green-500/20";
    } else {
      classes += " bg-gray-500/10 text-gray-600 border-gray-500/20";
    }
  }

  if (type === "healing") {
    if (value === "applied") {
      classes += " bg-green-500/10 text-green-600 border-green-500/20";
    } else if (value === "suggested") {
      classes += " bg-blue-500/10 text-blue-600 border-blue-500/20";
    } else if (value === "pending") {
      classes += " bg-yellow-500/10 text-yellow-600 border-yellow-500/20";
    } else if (value === "rejected") {
      classes += " bg-red-500/10 text-red-600 border-red-500/20";
    } else {
      classes += " bg-gray-500/10 text-gray-600 border-gray-500/20";
    }
  }

  if (type === "risk") {
    if (value === "high") {
      classes += " bg-red-500/10 text-red-600 border-red-500/20";
    } else if (value === "medium") {
      classes += " bg-yellow-500/10 text-yellow-600 border-yellow-500/20";
    } else if (value === "low") {
      classes += " bg-green-500/10 text-green-600 border-green-500/20";
    } else {
      classes += " bg-gray-500/10 text-gray-600 border-gray-500/20";
    }
  }

  if (type === "rootCause") {
    if (value.includes("locator")) {
      classes += " bg-blue-500/10 text-blue-600 border-blue-500/20";
    } else if (value.includes("sync")) {
      classes += " bg-yellow-500/10 text-yellow-600 border-yellow-500/20";
    } else if (value.includes("environment")) {
      classes += " bg-purple-500/10 text-purple-600 border-purple-500/20";
    } else if (value.includes("assert")) {
      classes += " bg-orange-500/10 text-orange-600 border-orange-500/20";
    } else {
      classes += " bg-gray-500/10 text-gray-600 border-gray-500/20";
    }
  }

  return <span className={classes}>{label}</span>;
}