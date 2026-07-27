"use client";

import { useState } from "react";

import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { DialogoEncerrarVinculo } from "@/componentes/paineis/cadastros/colaboradores/dialogo-encerrar-vinculo";
import {
  FormularioVinculo,
  paraCorpoDeVinculo,
  type ValoresFormularioVinculo,
} from "@/componentes/paineis/cadastros/colaboradores/formulario-vinculo";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { useContratos } from "@/ganchos/use-contratos";
import { useCriarVinculo, useVinculos } from "@/ganchos/use-vinculos";
import { formatarData } from "@/lib/formatacao";
import type { Esquema } from "@/lib/api";

interface SecaoVinculosProps {
  colaborador: Esquema<"Colaborador">;
  cargos: Esquema<"Cargo">[];
  departamentos: Esquema<"Departamento">[];
  centrosCusto: Esquema<"CentroCusto">[];
  unidades: Esquema<"Unidade">[];
}

const SELO_POR_STATUS: Record<string, "sucesso" | "atencao" | "neutro"> = {
  ativo: "sucesso",
  suspenso: "atencao",
  encerrado: "neutro",
};

/**
 * **Nenhum botão de "editar vínculo" genérico** — o contrato não tem
 * `atualizarVinculo` (só `criarVinculo` e `encerrarVinculo`, achado §2/§6 do
 * PCF). A única ação disponível sobre um vínculo ativo é "Encerrar".
 */
export function SecaoVinculos({
  colaborador,
  cargos,
  departamentos,
  centrosCusto,
  unidades,
}: SecaoVinculosProps) {
  const consulta = useVinculos({ colaboradorId: colaborador.id });
  const contratos = useContratos({ colaboradorId: colaborador.id });
  const criar = useCriarVinculo();
  const [dialogoAberto, setDialogoAberto] = useState(false);
  const [encerrando, setEncerrando] = useState<Esquema<"Vinculo"> | null>(null);

  function salvar(valores: ValoresFormularioVinculo) {
    if (!colaborador.id || !colaborador.empresaId) return;
    const corpo = paraCorpoDeVinculo(valores, colaborador.id, colaborador.empresaId);
    criar.mutate(corpo, { onSuccess: () => setDialogoAberto(false) });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Botao tamanho="compacto" onClick={() => setDialogoAberto(true)}>
          Novo vínculo
        </Botao>
      </div>

      {consulta.isPending ? (
        <Esqueleto className="h-24 w-full" />
      ) : consulta.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
        </Alerta>
      ) : (consulta.data?.dados ?? []).length === 0 ? (
        <p className="estilo-corpo text-texto-secundario">Nenhum vínculo cadastrado.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {(consulta.data?.dados ?? []).map((vinculo) => (
            <li
              key={vinculo.id}
              className="flex items-center justify-between gap-3 rounded-pequeno border border-borda-sutil p-3"
            >
              <div>
                <p className="estilo-corpo text-texto-primario">
                  {vinculo.tipoVinculo ?? "—"} {vinculo.principal ? "· principal" : ""}
                </p>
                <p className="estilo-legenda text-texto-secundario">
                  Matrícula eSocial {vinculo.matriculaEsocial ?? "—"} · desde{" "}
                  {vinculo.dataInicio ? formatarData(vinculo.dataInicio) : "—"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Selo variant={SELO_POR_STATUS[vinculo.status ?? ""] ?? "neutro"}>
                  {vinculo.status ?? "—"}
                </Selo>
                {vinculo.status === "ativo" ? (
                  <Botao
                    variant="destrutiva"
                    tamanho="compacto"
                    onClick={() => {
                      setEncerrando(vinculo);
                    }}
                  >
                    Encerrar
                  </Botao>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <Dialogo open={dialogoAberto} onOpenChange={setDialogoAberto}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>Novo vínculo</DialogoTitulo>
          </DialogoCabecalho>
          <FormularioVinculo
            contratos={contratos.data?.dados ?? []}
            cargos={cargos}
            departamentos={departamentos}
            centrosCusto={centrosCusto}
            unidades={unidades}
            salvando={criar.isPending}
            erro={criar.isError ? mensagemDeErroApi(criar.error) : undefined}
            aoSalvar={salvar}
            aoCancelar={() => setDialogoAberto(false)}
          />
        </DialogoConteudo>
      </Dialogo>

      <DialogoEncerrarVinculo vinculo={encerrando} aoFechar={() => setEncerrando(null)} />
    </div>
  );
}
