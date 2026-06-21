"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

type Provider = string | null | undefined;

interface ChannelIconProps {
  provider?: Provider;
  size?: number;
  className?: string;
  /** Renderiza só o glifo (sem o "tile" colorido de fundo). */
  bare?: boolean;
}

function isInstagram(provider: Provider) {
  return provider === "instagram";
}

/** Glifo do WhatsApp (telefone na bolha). */
export function BrandWhatsApp({ size = 20, className, bare = false }: Omit<ChannelIconProps, "provider">) {
  const box = Math.round(size);
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center",
        !bare && "rounded-[28%]",
        className,
      )}
      style={{
        width: box,
        height: box,
        background: bare ? undefined : "linear-gradient(135deg, #25D366 0%, #128C7E 100%)",
      }}
      aria-label="WhatsApp"
    >
      <svg
        width={Math.round(box * (bare ? 1 : 0.66))}
        height={Math.round(box * (bare ? 1 : 0.66))}
        viewBox="0 0 24 24"
        fill={bare ? "#25D366" : "#ffffff"}
        aria-hidden="true"
      >
        <path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.46 1.32 4.97L2 22l5.25-1.38a9.9 9.9 0 0 0 4.79 1.22h.01c5.46 0 9.91-4.45 9.91-9.91 0-2.65-1.03-5.14-2.9-7.01A9.82 9.82 0 0 0 12.04 2Zm5.52 12.34c-.21.58-1.2 1.11-1.68 1.18-.43.06-.97.09-1.56-.1-.36-.11-.82-.26-1.41-.52-2.5-1.07-4.13-3.58-4.25-3.74-.12-.16-1.01-1.34-1.01-2.56 0-1.22.64-1.82.86-2.07.23-.25.5-.31.66-.31h.48c.15.01.36-.05.56.43.2.5.7 1.72.76 1.84.06.12.1.27.02.43-.09.16-.13.26-.25.41-.12.14-.26.32-.37.43-.12.12-.25.25-.11.5.15.25.64 1.06 1.38 1.72.94.84 1.74 1.11 1.99 1.23.25.12.39.1.54-.06.15-.17.63-.72.79-.97.17-.24.33-.2.56-.12.22.08 1.44.68 1.69.8.25.12.41.18.47.28.07.11.07.6-.14 1.18Z" />
      </svg>
    </span>
  );
}

/** Glifo do Instagram com o gradiente característico (amarelo→rosa→roxo). */
export function BrandInstagram({ size = 20, className }: Omit<ChannelIconProps, "provider" | "bare">) {
  const box = Math.round(size);
  const gid = useId().replace(/:/g, "");
  return (
    <span
      className={cn("inline-flex shrink-0 items-center justify-center", className)}
      style={{ width: box, height: box }}
      aria-label="Instagram"
    >
      <svg width={box} height={box} viewBox="0 0 24 24" aria-hidden="true">
        <defs>
          <linearGradient id={`ig-${gid}`} x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#feda75" />
            <stop offset="25%" stopColor="#fa7e1e" />
            <stop offset="50%" stopColor="#d62976" />
            <stop offset="75%" stopColor="#962fbf" />
            <stop offset="100%" stopColor="#4f5bd5" />
          </linearGradient>
        </defs>
        <rect x="1.5" y="1.5" width="21" height="21" rx="6" fill={`url(#ig-${gid})`} />
        <rect
          x="6"
          y="6"
          width="12"
          height="12"
          rx="3.6"
          fill="none"
          stroke="#ffffff"
          strokeWidth="1.6"
        />
        <circle cx="12" cy="12" r="3" fill="none" stroke="#ffffff" strokeWidth="1.6" />
        <circle cx="16.2" cy="7.8" r="1.1" fill="#ffffff" />
      </svg>
    </span>
  );
}

export function ChannelIcon({ provider, size = 20, className, bare }: ChannelIconProps) {
  if (isInstagram(provider)) {
    return <BrandInstagram size={size} className={className} />;
  }
  // official / evolution / desconhecido → WhatsApp.
  return <BrandWhatsApp size={size} className={className} bare={bare} />;
}
