"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageCircle,
  MessagesSquare,
  Send,
  Users,
  UsersRound,
  Workflow,
} from "lucide-react";

import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";

interface Item {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const items: Item[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/canais", label: "Canais", icon: MessageCircle },
  { href: "/workflows", label: "Workflows", icon: Workflow },
  { href: "/broadcasts", label: "Broadcasts", icon: Send },
  { href: "/conversations", label: "Conversas", icon: MessagesSquare },
  { href: "/contatos", label: "Contatos", icon: Users },
  { href: "/usuarios", label: "Usuários", icon: UsersRound, adminOnly: true },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const visible = items.filter((i) => !i.adminOnly || user?.is_admin);

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r bg-background">
      <div className="flex h-14 items-center border-b px-4 text-sm font-semibold">
        Mensageria
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-2">
        {visible.map((item) => {
          // Dashboard é exact match; outros usam startsWith
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname?.startsWith(item.href);
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
