import { cn } from "@/lib/utils";

type LogoSize = "sm" | "md" | "lg";

const SIZE_MAP: Record<
  LogoSize,
  { box: string; icon: number; text: string }
> = {
  sm: { box: "w-7 h-7 rounded-md", icon: 16, text: "text-base" },
  md: { box: "w-9 h-9 rounded-lg", icon: 20, text: "text-lg" },
  lg: { box: "w-12 h-12 rounded-xl", icon: 28, text: "text-2xl" },
};

function Mark({ className, iconSize = 20 }: { className?: string; iconSize?: number }) {
  return (
    <div
      className={cn(
        "flex items-center justify-center shadow-[0_4px_12px_rgba(16,185,129,0.25)]",
        className,
      )}
      style={{
        background: "linear-gradient(135deg, #34D399 0%, #059669 100%)",
      }}
    >
      <svg
        width={iconSize}
        height={iconSize}
        viewBox="0 0 24 24"
        fill="none"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3 12c2-3 4-3 6 0s4 3 6 0 4-3 6 0" />
      </svg>
    </div>
  );
}

interface LogoProps {
  className?: string;
  textClassName?: string;
  showText?: boolean;
  size?: LogoSize;
}

export function Logo({
  className,
  textClassName,
  showText = true,
  size = "md",
}: LogoProps) {
  const s = SIZE_MAP[size];
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <Mark className={s.box} iconSize={s.icon} />
      {showText && (
        <span
          className={cn(
            "font-bold tracking-tight",
            s.text,
            textClassName,
          )}
        >
          Whats<span className="text-emerald-500">Flow</span>
        </span>
      )}
    </div>
  );
}

export function LogoMark({
  className,
  size = "md",
}: {
  className?: string;
  size?: LogoSize;
}) {
  const s = SIZE_MAP[size];
  return <Mark className={cn(s.box, className)} iconSize={s.icon} />;
}
