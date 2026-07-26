import type { ReactNode } from "react";

import { formatarHora } from "@/lib/formatacao/data";
import { cn } from "@/lib/utils";

/**
 * Canal de origem da marcação (`packages/contracts/glossario.md`, verbete
 * "Canal"). `importacao` existe no contrato mas não aparece tipicamente numa
 * linha do tempo ao vivo — incluído mesmo assim para não haver `as any`.
 */
export type CanalDeMarcacao = "terminal" | "mobile" | "web" | "totem" | "api" | "importacao";

export type SentidoInformado = "entrada" | "saida" | "indefinido";

export type ClassificacaoDeConfianca = "alta" | "media" | "baixa" | "bloqueada";

/**
 * Estado de exibição da marcação na linha do tempo. Não é o mesmo campo que
 * `classificacaoConfianca` do contrato: aqui é uma leitura de apresentação
 * que combina confiança e situação de sincronismo (offline pendente).
 */
export type EstadoDeMarcacao = "normal" | "suspeita" | "pendenteEnvioOffline";

export interface MarcacaoDaLinhaDoTempo {
  id: string;
  /** ISO 8601. É o instante do FATO (`Marcacao.datahoraMarcacao` no contrato). */
  datahoraMarcacao: string;
  canal: CanalDeMarcacao;
  /** Número Sequencial de Registro. Ausente quando a marcação ainda não foi confirmada pelo REP-P (fila offline). */
  nsr?: number;
  scoreConfianca?: number;
  classificacaoConfianca?: ClassificacaoDeConfianca;
  /**
   * Sentido informado pelo COLETOR (nunca inferido por este componente — o
   * REP-P legalmente não registra "entrada" ou "saída", ver glossário).
   */
  sentidoInformado?: SentidoInformado;
  estado?: EstadoDeMarcacao;
}

export interface LinhaDoTempoDeMarcacoesProps {
  marcacoes: MarcacaoDaLinhaDoTempo[];
  /** Densidade compacta (RH revisando muitas linhas) ou confortável (colaborador vendo o próprio dia). */
  densidade?: "compacta" | "confortavel";
  fusoHorario?: string;
  /** Texto mostrado quando `marcacoes` está vazio. */
  mensagemVazia?: string;
}

const ROTULO_CANAL: Record<CanalDeMarcacao, string> = {
  terminal: "Terminal",
  mobile: "Celular",
  web: "Web",
  totem: "Totem",
  api: "API",
  importacao: "Importação",
};

const ROTULO_SENTIDO: Record<SentidoInformado, string> = {
  entrada: "Entrada informada",
  saida: "Saída informada",
  indefinido: "Sentido não informado",
};

function RotuloDeEstado({ estado }: { estado: EstadoDeMarcacao }): ReactNode {
  // Cor nunca e o unico portador (WCAG 1.4.1): cada estado tem tambem um
  // rotulo textual e um marcador de forma distinta no prefixo do texto.
  if (estado === "suspeita") {
    return (
      <span className="estilo-rotulo inline-flex items-center gap-1 rounded-pequeno bg-estado-atencao-fundo px-1 py-micro text-estado-atencao-texto">
        <span aria-hidden="true">▲</span>
        Suspeita
      </span>
    );
  }
  if (estado === "pendenteEnvioOffline") {
    return (
      <span className="estilo-rotulo inline-flex items-center gap-1 rounded-pequeno bg-estado-info-fundo px-1 py-micro text-estado-info-texto">
        <span aria-hidden="true">⏳</span>
        Pendente de envio (offline)
      </span>
    );
  }
  return (
    <span className="estilo-rotulo inline-flex items-center gap-1 rounded-pequeno bg-estado-sucesso-fundo px-1 py-micro text-estado-sucesso-texto">
      <span aria-hidden="true">●</span>
      Normal
    </span>
  );
}

/**
 * Sequência de marcações de um dia ou período, em ordem cronológica.
 *
 * Regra de domínio inegociável: o REP-P não registra "entrada" ou "saída" —
 * o pareamento é feito depois, na apuração (fase F4). Este componente por
 * isso NUNCA infere sentido a partir da posição na lista; se um sentido
 * aparece, é porque `sentidoInformado` veio preenchido pelo coletor.
 */
export function LinhaDoTempoDeMarcacoes({
  marcacoes,
  densidade = "confortavel",
  fusoHorario,
  mensagemVazia = "Nenhuma marcação neste período.",
}: LinhaDoTempoDeMarcacoesProps) {
  if (marcacoes.length === 0) {
    return (
      <p className="estilo-corpo rounded-medio border border-borda-sutil bg-fundo-sutil px-3 py-2 text-texto-secundario">
        {mensagemVazia}
      </p>
    );
  }

  const espacamentoItem = densidade === "compacta" ? "py-1" : "py-2";

  return (
    <ol className="flex flex-col divide-y divide-borda-sutil" aria-label="Linha do tempo de marcações">
      {marcacoes.map((marcacao) => (
        <li key={marcacao.id} className={cn("flex items-start gap-3", espacamentoItem)}>
          <time
            dateTime={marcacao.datahoraMarcacao}
            className="estilo-tabular w-14 shrink-0 pt-micro text-texto-primario"
          >
            {formatarHora(marcacao.datahoraMarcacao, fusoHorario)}
          </time>

          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="estilo-corpo text-texto-primario">{ROTULO_CANAL[marcacao.canal]}</span>
              {marcacao.sentidoInformado ? (
                <span className="estilo-legenda text-texto-terciario">
                  {ROTULO_SENTIDO[marcacao.sentidoInformado]}
                </span>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <RotuloDeEstado estado={marcacao.estado ?? "normal"} />
              {marcacao.nsr !== undefined ? (
                <span className="estilo-identificador text-texto-terciario">NSR {marcacao.nsr}</span>
              ) : null}
              {marcacao.scoreConfianca !== undefined ? (
                <span className="estilo-legenda text-texto-terciario">
                  Confiança {marcacao.scoreConfianca}/100
                  {marcacao.classificacaoConfianca ? ` (${marcacao.classificacaoConfianca})` : ""}
                </span>
              ) : null}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
