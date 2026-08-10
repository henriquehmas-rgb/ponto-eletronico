"use client";

import { useState } from "react";

import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";
import { Selo } from "@/componentes/ui/badge";
import { Botao } from "@/componentes/ui/button";
import { Dialogo, DialogoCabecalho, DialogoConteudo, DialogoTitulo } from "@/componentes/ui/dialog";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { AreaDeTexto } from "@/componentes/ui/textarea";
import {
  type MarcacaoSuspeita,
  useDecidirRevisaoMarcacao,
  useMarcacoesSuspeitas,
} from "@/ganchos/use-marcacoes-suspeitas";
import { formatarDataHora } from "@/lib/formatacao";
import { PortaoDePermissao } from "@/lib/permissoes";
import { useSessaoCompleta } from "@/ganchos/use-sessao-completa";
import { temPermissao } from "@/lib/permissoes/tem-permissao";

const SELO_POR_CLASSIFICACAO: Record<string, "sucesso" | "atencao" | "erro" | "neutro"> = {
  alta: "sucesso",
  media: "atencao",
  baixa: "erro",
  bloqueada: "erro",
};

/** Círculo de score: mesmo par fundo+texto do Selo de classificação
 * (`estado.<x>Fundo`/`estado.<x>Texto`), nunca cor isolada. */
const CIRCULO_POR_CLASSIFICACAO: Record<string, string> = {
  alta: "bg-estado-sucesso-fundo text-estado-sucesso-texto",
  media: "bg-estado-atencao-fundo text-estado-atencao-texto",
  baixa: "bg-estado-erro-fundo text-estado-erro-texto",
  bloqueada: "bg-estado-erro-fundo text-estado-erro-texto",
};

interface SinalExplicabilidade {
  sinal: string;
  categoria: string;
  disponibilidade: string;
  valor: unknown;
  pesoEfetivo: number;
  pontuacao: number | null;
  contribuicao: number | null;
}

interface BlocoExplicabilidade {
  versaoMotor: number;
  perfilConfianca: string;
  limiarBloqueio: number;
  limiarRevisao: number;
  scoreExplicabilidade: SinalExplicabilidade[];
}

/** `flagsIntegridade["_antifraude"]` (`app.antifraude.explicabilidade`,
 * chave reservada computada pelo servidor -- ver docstring daquele módulo).
 * Leitura defensiva: campo é `additionalProperties: true` no contrato, sem
 * schema tipado do lado do servidor para o bloco interno. */
function extrairExplicabilidade(
  flagsIntegridade: MarcacaoSuspeita["item"]["flagsIntegridade"],
): BlocoExplicabilidade | undefined {
  const bloco = (flagsIntegridade as Record<string, unknown> | undefined)?.["_antifraude"];
  if (!bloco || typeof bloco !== "object") return undefined;
  return bloco as BlocoExplicabilidade;
}

export default function PaginaDeAntifraude() {
  const { sessao } = useSessaoCompleta();
  const temPermissaoSensivel = temPermissao(sessao, "marcacoes.ler_sensivel");
  const consulta = useMarcacoesSuspeitas({ habilitado: temPermissaoSensivel });
  const [detalhe, setDetalhe] = useState<MarcacaoSuspeita | null>(null);

  const itens = consulta.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="estilo-titulo-pagina text-texto-primario">Marcações suspeitas</h1>
        <p className="estilo-corpo text-texto-secundario">
          Marcações gravadas com score de confiança entre os limiares de bloqueio e revisão
          (ADR-008) — a marcação é válida e já conta no espelho; esta fila é só para o gestor
          revisar o contexto e, quando aplicável, abrir um tratamento.
        </p>
      </header>

      <PortaoDePermissao
        permissao="marcacoes.ler_sensivel"
        fallback={
          <Alerta variant="atencao">
            <AlertaTitulo>Permissão necessária</AlertaTitulo>
            <AlertaDescricao>
              Esta tela exige a permissão &quot;marcacoes.ler_sensivel&quot; (mesma exigida por
              &quot;Obter contexto antifraude da marcação&quot; no contrato) — fale com o
              administrador do seu tenant.
            </AlertaDescricao>
          </Alerta>
        }
      >
        {consulta.isError ? (
          <Alerta variant="erro">
            <AlertaDescricao>{mensagemDeErroApi(consulta.error)}</AlertaDescricao>
          </Alerta>
        ) : null}

        {consulta.isPending ? (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 3 }).map((_, indice) => (
              <Esqueleto key={indice} className="w-full rounded-suave" style={{ height: 94 }} />
            ))}
          </div>
        ) : itens.length === 0 ? (
          <div className="rounded-suave border border-dashed border-borda-padrao p-6 text-center">
            <p className="estilo-corpo text-texto-secundario">
              Nenhuma marcação pendente de revisão.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {itens.map((item) => {
              const classificacao = item.item.classificacaoConfianca ?? "";
              const bloco = extrairExplicabilidade(item.item.flagsIntegridade);
              const sinais = (bloco?.scoreExplicabilidade ?? []).filter(
                (sinal) => sinal.disponibilidade === "real" && (sinal.contribuicao ?? 0) > 0,
              );
              return (
                <div
                  key={item.item.marcacaoId}
                  className="flex flex-wrap items-center gap-4 rounded-suave bg-fundo-superficie p-[var(--espacamento-4)] shadow-flutuante-cartao"
                >
                  <div
                    className={
                      "flex shrink-0 flex-col items-center justify-center rounded-pleno " +
                      (CIRCULO_POR_CLASSIFICACAO[classificacao] ?? "bg-fundo-sutil text-texto-secundario")
                    }
                    style={{ width: 58, height: 58 }}
                  >
                    <span className="font-mono text-lg font-semibold leading-none tabular-nums">
                      {item.item.scoreConfianca ?? "—"}
                    </span>
                    <span className="text-3xs font-semibold uppercase opacity-80">Score</span>
                  </div>

                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      className="text-left text-sm font-medium text-texto-primario hover:underline"
                      onClick={() => setDetalhe(item)}
                    >
                      {item.nomeColaborador ?? item.item.colaboradorId ?? "—"}
                    </button>
                    <p className="mt-0.5 text-xs text-texto-terciario">
                      {item.item.canal ?? "—"} ·{" "}
                      {item.item.datahoraMarcacao ? formatarDataHora(item.item.datahoraMarcacao) : "—"}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Selo variant={SELO_POR_CLASSIFICACAO[classificacao] ?? "neutro"}>
                        {classificacao || "—"}
                      </Selo>
                      {sinais.map((sinal) => (
                        <Selo key={sinal.sinal} variant="atencao">
                          {sinal.sinal}
                        </Selo>
                      ))}
                    </div>
                  </div>

                  <Botao
                    variant="secundaria"
                    tamanho="compacto"
                    className="rounded-pleno"
                    onClick={() => setDetalhe(item)}
                  >
                    Ver e decidir
                  </Botao>
                </div>
              );
            })}
          </div>
        )}
      </PortaoDePermissao>

      <Dialogo open={detalhe !== null} onOpenChange={(aberto) => !aberto && setDetalhe(null)}>
        <DialogoConteudo className="sm:max-w-2xl">
          <DialogoCabecalho>
            <DialogoTitulo>Explicabilidade do score</DialogoTitulo>
          </DialogoCabecalho>
          {detalhe ? (
            <DetalheExplicabilidade item={detalhe} aoDecidir={() => setDetalhe(null)} />
          ) : null}
        </DialogoConteudo>
      </Dialogo>
    </div>
  );
}

function DetalheExplicabilidade({
  item,
  aoDecidir,
}: {
  item: MarcacaoSuspeita;
  aoDecidir: () => void;
}) {
  const bloco = extrairExplicabilidade(item.item.flagsIntegridade);
  const decidir = useDecidirRevisaoMarcacao();
  const [observacao, setObservacao] = useState("");

  function registrarDecisao(decisao: "aprovada" | "rejeitada") {
    const texto = observacao.trim();
    decidir.mutate(
      {
        marcacaoId: item.item.marcacaoId,
        corpo: texto ? { decisao, observacao: texto } : { decisao },
      },
      { onSuccess: aoDecidir },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-texto-terciario">Colaborador</dt>
        <dd>{item.nomeColaborador ?? item.item.colaboradorId}</dd>
        <dt className="text-texto-terciario">Score composto</dt>
        <dd>
          {item.item.scoreConfianca} ({item.item.classificacaoConfianca})
        </dd>
        <dt className="text-texto-terciario">Perfil de confiança</dt>
        <dd>{bloco?.perfilConfianca ?? "—"}</dd>
      </dl>

      {bloco ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-borda-sutil text-left text-texto-terciario">
                <th className="py-1 pr-2">Sinal</th>
                <th className="py-1 pr-2">Categoria</th>
                <th className="py-1 pr-2">Disponibilidade</th>
                <th className="py-1 pr-2">Peso</th>
                <th className="py-1 pr-2">Pontuação</th>
                <th className="py-1">Contribuição</th>
              </tr>
            </thead>
            <tbody>
              {bloco.scoreExplicabilidade.map((sinal) => (
                <tr key={sinal.sinal} className="border-b border-borda-sutil/50">
                  <td className="py-1 pr-2">{sinal.sinal}</td>
                  <td className="py-1 pr-2">{sinal.categoria}</td>
                  <td className="py-1 pr-2">
                    {sinal.disponibilidade === "real" ? (
                      <Selo variant="sucesso">real</Selo>
                    ) : (
                      <Selo variant="neutro">não aplicável</Selo>
                    )}
                  </td>
                  <td className="py-1 pr-2 tabular-nums">{sinal.pesoEfetivo.toFixed(1)}</td>
                  <td className="py-1 pr-2 tabular-nums">{sinal.pontuacao?.toFixed(1) ?? "—"}</td>
                  <td className="py-1 tabular-nums">{sinal.contribuicao?.toFixed(1) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-texto-terciario">Explicabilidade não disponível para esta marcação.</p>
      )}

      {decidir.isError ? (
        <Alerta variant="erro">
          <AlertaDescricao>{mensagemDeErroApi(decidir.error)}</AlertaDescricao>
        </Alerta>
      ) : null}

      <div className="flex flex-col gap-2">
        <label htmlFor="observacao-revisao" className="estilo-legenda text-texto-secundario">
          Observação (opcional)
        </label>
        <AreaDeTexto
          id="observacao-revisao"
          value={observacao}
          onChange={(evento) => setObservacao(evento.target.value)}
          placeholder="Ex.: confirmado com o colaborador, app de mapa aberto em segundo plano."
          disabled={decidir.isPending}
        />
      </div>

      <div className="flex justify-end gap-2">
        <Botao
          variant="secundaria"
          onClick={() => registrarDecisao("rejeitada")}
          disabled={decidir.isPending}
        >
          Rejeitar
        </Botao>
        <Botao onClick={() => registrarDecisao("aprovada")} disabled={decidir.isPending}>
          Aprovar
        </Botao>
      </div>
    </div>
  );
}
