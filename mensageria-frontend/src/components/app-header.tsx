"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, LogOut, UserCircle, UsersRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/contexts/auth-context";

const BREADCRUMB: Record<string, string> = {
  "/": "Dashboard",
  "/canais": "Canais",
  "/workflows": "Workflows",
  "/broadcasts": "Broadcasts",
  "/conversations": "Conversas",
  "/contatos": "Contatos",
  "/usuarios": "Usuários",
  "/perfil": "Perfil",
};

function resolveBreadcrumb(pathname: string | null): string {
  if (!pathname) return "";
  if (BREADCRUMB[pathname]) return BREADCRUMB[pathname];
  // /workflows/[id]
  if (pathname.startsWith("/workflows/")) return "Workflows › Editar";
  // fallback: maior prefixo match
  for (const key of Object.keys(BREADCRUMB)) {
    if (key !== "/" && pathname.startsWith(key)) return BREADCRUMB[key];
  }
  return "";
}

function initials(nameOrEmail: string): string {
  const base = (nameOrEmail || "").trim();
  if (!base) return "?";
  // Se tem espaço, pega primeira letra de cada uma das 2 primeiras palavras
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  // Single word (ou email): 2 primeiras letras
  return base.slice(0, 2).toUpperCase();
}

export function AppHeader() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const crumb = resolveBreadcrumb(pathname);
  const displayName = user?.name || user?.email || "";

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4">
      <div className="text-sm font-medium text-foreground">{crumb}</div>
      <div className="flex items-center gap-1">
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-2 px-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500/15 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                {initials(displayName)}
              </span>
              <span className="hidden max-w-[160px] truncate text-sm md:inline">
                {displayName}
              </span>
              <ChevronDown className="h-3 w-3 opacity-60" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel className="truncate text-xs font-normal text-muted-foreground">
              {user?.email}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/perfil">
                <UserCircle className="mr-2 h-4 w-4" /> Perfil
              </Link>
            </DropdownMenuItem>
            {user?.is_admin && (
              <DropdownMenuItem asChild>
                <Link href="/usuarios">
                  <UsersRound className="mr-2 h-4 w-4" /> Usuários
                </Link>
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={logout}
              className="text-destructive focus:text-destructive"
            >
              <LogOut className="mr-2 h-4 w-4" /> Sair
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
