import { motion, useReducedMotion } from "framer-motion";

/** Calibrated-confidence ring. Values come from the backend calibration. */
export function ConfidenceRing({
  value,
  level,
  method,
  size = 148,
}: {
  value: number | null | undefined;
  level?: string | null;
  method?: string | null;
  size?: number;
}) {
  const reduceMotion = useReducedMotion();
  if (value === null || value === undefined) {
    return <div className="flex h-36 items-center justify-center text-2xs text-ink-3">no calibrated probability</div>;
  }
  const radius = size / 2 - 10;
  const circumference = 2 * Math.PI * radius;
  const filled = Math.max(0, Math.min(1, value)) * circumference;
  const tone = value >= 0.9 ? "var(--green)" : value >= 0.7 ? "var(--amber)" : "var(--red)";
  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Calibrated confidence ${(value * 100).toFixed(1)} percent`}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgb(var(--line) / 0.35)" strokeWidth={7} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth={7}
          strokeLinecap="round"
          strokeDasharray={circumference}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          initial={reduceMotion ? false : { strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - filled }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        />
        <text x="50%" y="47%" textAnchor="middle" fill="#e8edf4" fontSize={size / 5} fontFamily="var(--font-mono)">
          {(value * 100).toFixed(1)}%
        </text>
        <text x="50%" y="62%" textAnchor="middle" fill="#5f7085" fontSize={9} fontFamily="var(--font-mono)" letterSpacing={2}>
          {level ?? ""}
        </text>
      </svg>
      <p className="text-center text-2xs leading-relaxed text-ink-3">
        calibrated probability · {method ?? "calibration method unavailable"}
        <br />
        confidence reflects model uncertainty, not physical certainty
      </p>
    </div>
  );
}
