import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

/** Counts up to a real backend value; never invents numbers. */
export function AnimatedNumber({
  value,
  digits = 0,
  duration = 0.7,
  suffix,
  prefix,
  className = "",
}: {
  value: number | null | undefined;
  digits?: number;
  duration?: number;
  suffix?: string;
  prefix?: string;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  const [display, setDisplay] = useState(value ?? 0);
  const previous = useRef(value ?? 0);

  useEffect(() => {
    if (value === null || value === undefined) return;
    if (reduceMotion) {
      setDisplay(value);
      previous.current = value;
      return;
    }
    const from = previous.current;
    const to = value;
    const started = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const progress = Math.min(1, (now - started) / (duration * 1000));
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(from + (to - from) * eased);
      if (progress < 1) frame = requestAnimationFrame(step);
      else previous.current = to;
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, reduceMotion]);

  if (value === null || value === undefined) {
    return <span className={`mono-value text-ink-3 ${className}`}>—</span>;
  }
  return (
    <span className={`mono-value ${className}`}>
      {prefix}
      {display.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}
      {suffix}
    </span>
  );
}

export function MotionSection({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.section
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: reduceMotion ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.section>
  );
}

export function HudPanel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  accent,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  accent?: string;
}) {
  return (
    <section className={`hud flex min-h-0 flex-col ${className}`} style={accent ? { borderColor: accent } : undefined}>
      {(title || actions) && (
        <header className="hud-title border-b border-line/60">
          <div className="min-w-0">
            {title && <h2 className="truncate text-2xs font-semibold uppercase tracking-[0.16em] text-ink-2">{title}</h2>}
            {subtitle && <p className="mt-0.5 truncate text-2xs text-ink-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}
