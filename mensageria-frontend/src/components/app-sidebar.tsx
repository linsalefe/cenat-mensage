"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageCircle,
  MessagesSquare,
  Users,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";

const items = [
  { href: "/canais", label: "Canais", icon: MessageCircle },
  { href: "/workflows", label: "Workflows", icon: Workflow },
  { href: "/conversations", label: "Conversas", icon: MessagesSquare },
  { href: "/contatos", label: "Contatos", icon: Users },
];

export function AppSidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r bg-background">
      <div className="flex h-14 items-center border-b px-4 text-sm font-semibold">
        Mensageria
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-2">
        {items.map((item) => {
          const active = pathname?.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded px-3 py-2 text-sm hover:bg-muted",
                active && "bg-muted font-medium",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
