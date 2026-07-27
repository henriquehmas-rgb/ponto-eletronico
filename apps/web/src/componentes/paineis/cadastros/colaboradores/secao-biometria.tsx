"use client";

import { useState } from "react";

import { DialogoConfirmacao } from "@/componentes/paineis/cadastros/_shared/dialogo-confirmacao";
import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useBiometrias, useRevogarBiometria, useValidarBiometria } from "@/ganchos/use-biometrias";
import { formatarDataHora } from "@/lib/formatacao";
import { PortaoDePermissao } from "@/lib/permissoes";
import type { Esquema } from "@/lib/api";

interface SecaoBiometriaProps {
  colaborador: Esquema<"Colaborador">;
}

const SELO_POR_STATUS: Record<string, "sucesso" | "atencao" | "erro" | "neutro"> = {
  ativa: "sucesso",
  pendente: "atencao",
  reprovada: "erro",
  revogada: "neutro",
  expirada: "neutro",
};

/**
 * Aba "Biometria" do colaborador (T8) — **apenas administração de matrículas
 * já existentes**: listar, revogar, aprovar/reprovar. Nenhum componente aqui
 * usa `getUserMedia` nem qualquer captura de câmera — cadastro de biometria
 * nova é F7/F8, fora desta fase. O vetor biométrico em si nunca é exibido
 * (a API nunca o expõe).
 */
export function SecaoBiometria({ colaborador }: SecaoBiometriaProps) {
  const consulta = useBiometrias({ colaboradorId: colaborador.id });
  const revogar = useRevogarBiometria();
  const validar = useValidarBiometria();
  const [revogando, setRevogando] = useState<Esquema<"Biometria"> | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <p className="estilo-legenda text-texto-secundario">
        Credenciais já enviadas por outro canal (terminal, app ou importação). Esta tela só revoga
        ou aprova — não captura biometria nova.
      </p>

      {consulta.isPending ? (
        <Esqueleto className="h-24 w-full" />
      ) : consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : (consulta.data?.dados ?? []).length === 0 ? (
        <p className="estilo-corpo text-texto-secundario">
          Nenhuma credencial biométrica cadastrada.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {(consulta.data?.dados ?? []).map((biometria) => (
            <li
              key={biometria.id}
              className="flex items-center justify-between gap-3 rounded-pequeno border border-borda-sutil p-3"
            >
              <div>
                <p className="estilo-corpo text-texto-primario">
                  {biometria.modalidade ?? "—"} · origem {biometria.origemCadastro ?? "—"}
                </p>
                <p className="estilo-legenda text-texto-secundario">
                  Cadastrada em{" "}
                  {biometria.cadastradaEm ? formatarDataHora(biometria.cadastradaEm) : "—"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Selo variant={SELO_POR_STATUS[biometria.status ?? ""] ?? "neutro"}>
                  {biometria.status ?? "—"}
                </Selo>
                {biometria.status === "pendente" ? (
                  <PortaoDePermissao permissao="biometrias.aprovar">
                    <Botao
                      variant="secundaria"
                      tamanho="compacto"
                      disabled={validar.isPending}
                      onClick={() => {
                        if (!biometria.id) return;
                        validar.mutate({ id: biometria.id, corpo: { decisao: "aprovar" } });
                      }}
                    >
                      Aprovar
                    </Botao>
                  </PortaoDePermissao>
                ) : null}
                {biometria.status !== "revogada" ? (
                  <PortaoDePermissao permissao="biometrias.excluir">
                    <Botao
                      variant="destrutiva"
                      tamanho="compacto"
                      onClick={() => {
                        setRevogando(biometria);
                      }}
                    >
                      Revogar
                    </Botao>
                  </PortaoDePermissao>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <DialogoConfirmacao
        aberto={Boolean(revogando)}
        aoMudarAberto={(aberto) => {
          if (!aberto) setRevogando(null);
        }}
        titulo="Revogar credencial biométrica"
        descricao="A credencial deixa de autenticar marcações e o expurgo do template é agendado conforme a política de retenção."
        rotuloConfirmar="Revogar"
        confirmando={revogar.isPending}
        erro={revogar.isError ? mensagemDeErroApi(revogar.error) : undefined}
        aoConfirmar={() => {
          if (!revogando?.id) return;
          revogar.mutate(revogando.id, { onSuccess: () => setRevogando(null) });
        }}
      />
    </div>
  );
}
