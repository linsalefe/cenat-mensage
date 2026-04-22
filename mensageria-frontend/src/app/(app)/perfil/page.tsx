"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

import { useAuth } from "@/contexts/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { profileApi } from "@/lib/api-profile";

function errMsg(err: unknown, fb = "Erro inesperado") {
  return axios.isAxiosError(err) && err.response?.data?.detail
    ? String(err.response.data.detail)
    : fb;
}

export default function PerfilPage() {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [savingName, setSavingName] = useState(false);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [changing, setChanging] = useState(false);

  useEffect(() => {
    if (user) setName(user.name || "");
  }, [user]);

  if (!user) return null;

  const onSaveName = async () => {
    setSavingName(true);
    try {
      await profileApi.update({ name });
      toast.success("Nome atualizado");
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setSavingName(false);
    }
  };

  const onChangePassword = async () => {
    if (next.length < 8) {
      toast.error("Nova senha precisa ter no mínimo 8 caracteres");
      return;
    }
    if (next !== confirm) {
      toast.error("Confirmação não bate com a nova senha");
      return;
    }
    setChanging(true);
    try {
      await profileApi.changePassword({
        current_password: current,
        new_password: next,
      });
      toast.success("Senha alterada");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : null;
      if (status === 401) toast.error("Senha atual incorreta");
      else toast.error(errMsg(err));
    } finally {
      setChanging(false);
    }
  };

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <h1 className="text-xl font-semibold">Perfil</h1>

      <Card>
        <CardHeader>
          <CardTitle>Dados da conta</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label>Email</Label>
            <Input value={user.email} readOnly className="bg-muted/40 font-mono text-xs" />
          </div>
          <div className="space-y-1">
            <Label>Nome</Label>
            <div className="flex gap-2">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
              <Button onClick={onSaveName} disabled={savingName || name === (user.name || "")}>
                {savingName ? "Salvando…" : "Salvar"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Alterar senha</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label>Senha atual</Label>
            <Input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div className="space-y-1">
            <Label>Nova senha (mín. 8)</Label>
            <Input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <div className="space-y-1">
            <Label>Confirmar nova senha</Label>
            <Input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <Button
            onClick={onChangePassword}
            disabled={changing || !current || !next || !confirm}
          >
            {changing ? "Alterando…" : "Alterar senha"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
