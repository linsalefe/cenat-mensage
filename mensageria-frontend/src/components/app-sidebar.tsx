"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutGrid,
  MessageSquare,
  MessagesSquare,
  Send,
  UserCog,
  Users,
  Workflow,
} from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { useAuth } from "@/contexts/auth-context";
import { cn } from "@/lib/utils";

interface Item {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const items: Item[] = [
  { href: "/", label: "Dashboard", icon: LayoutGrid },
  { href: "/canais", label: "Canais", icon: MessageSquare },
  { href: "/workflows", label: "Workflows", icon: Workflow },
  { href: "/broadcasts", label: "Broadcasts", icon: Send },
  { href: "/conversations", label: "Conversas", icon: MessagesSquare },
  { href: "/contatos", label: "Contatos", icon: Users },
  { href: "/usuarios", label: "Usuários", icon: UserCog, adminOnly: true },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const visible = items.filter((i) => !i.adminOnly || user?.is_admin);

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r bg-background">
      <div className="flex h-16 items-center border-b px-4">
        <Logo size="md" />
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-3 pt-4">
        {visible.map((item) => {
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
                "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-l-2 border-emerald-500 pl-[calc(0.75rem-2px)]"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
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
