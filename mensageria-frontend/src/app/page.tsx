"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/contexts/auth-context";

export default function HomePage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    router.replace(user ? "/canais" : "/login");
  }, [isLoading, user, router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-sm text-muted-foreground">Carregando…</div>
    </div>
  );
}
