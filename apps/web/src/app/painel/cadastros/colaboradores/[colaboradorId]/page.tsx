"use client";

import Link from "next/link";
import { use } from "react";

import { mensagemDeErroApi } from "@/componentes/paineis/cadastros/_shared/erro-amigavel";
import {
  FormularioColaborador,
  paraCorpoDeColaborador,
  type ValoresFormularioColaborador,
} from "@/componentes/paineis/cadastros/colaboradores/formulario-colaborador";
import { SecaoBiometria } from "@/componentes/paineis/cadastros/colaboradores/secao-biometria";
import { SecaoContratos } from "@/componentes/paineis/cadastros/colaboradores/secao-contratos";
import { SecaoGestores } from "@/componentes/paineis/cadastros/colaboradores/secao-gestores";
import { SecaoVinculos } from "@/componentes/paineis/cadastros/colaboradores/secao-vinculos";
import { Alerta, AlertaDescricao } from "@/componentes/ui/alert";
import { Esqueleto } from "@/componentes/ui/skeleton";
import { Abas, AbaGatilho, ConteudoDaAba, ListaDeAbas } from "@/componentes/ui/tabs";
import {
  useAtualizarColaborador,
  useColaborador,
  useColaboradores,
} from "@/ganchos/use-colaboradores";
import { useCargos } from "@/ganchos/use-cargos";
import { useCentrosCusto } from "@/ganchos/use-centros-custo";
import { useDepartamentos } from "@/ganchos/use-departamentos";
import { useEmpresas } from "@/ganchos/use-empresas";
import { useUnidades } from "@/ganchos/use-unidades";

interface PaginaProps {
  params: Promise<{ colaboradorId: string }>;
}

export default function PaginaDeDetalheDoColaborador({ params }: PaginaProps) {
  const { colaboradorId } = use(params);
  const colaborador = useColaborador(colaboradorId);
  const empresas = useEmpresas({ ativo: true });
  const atualizar = useAtualizarColaborador();

  const empresaId = colaborador.data?.empresaId;
  const cargos = useCargos({ empresaId, ativo: true });
  const departamentos = useDepartamentos({ empresaId, ativo: true });
  const centrosCusto = useCentrosCusto({ empresaId, ativo: true });
  const unidades = useUnidades({ empresaId, ativo: true });
  const colaboradores = useColaboradores({ empresaId, limite: 200 });

  if (colaborador.isPending) {
    return <Esqueleto className="h-64 w-full" />;
  }
  if (colaborador.isError || !colaborador.data) {
    return (
      <Alerta variant="erro">
        <AlertaDescricao>{mensagemDeErroApi(colaborador.error)}</AlertaDescricao>
      </Alerta>
    );
  }

  const dados = colaborador.data;

  function salvarDados(valores: ValoresFormularioColaborador) {
    if (!colaboradorId) return;
    atualizar.mutate({ id: colaboradorId, corpo: paraCorpoDeColaborador(valores) });
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link
            href="/painel/cadastros/colaboradores"
            className="estilo-legenda text-texto-secundario hover:underline"
          >
            ← Colaboradores
          </Link>
          <h1 className="estilo-titulo-pagina text-texto-primario">
            {dados.nomeSocial ?? dados.nomeCompleto}
          </h1>
        </div>
      </header>

      <Abas defaultValue="dados">
        <ListaDeAbas>
          <AbaGatilho value="dados">Dados</AbaGatilho>
          <AbaGatilho value="vinculos">Vínculos</AbaGatilho>
          <AbaGatilho value="contratos">Contratos</AbaGatilho>
          <AbaGatilho value="gestores">Gestores</AbaGatilho>
          <AbaGatilho value="biometria">Biometria</AbaGatilho>
        </ListaDeAbas>

        <ConteudoDaAba value="dados">
          <FormularioColaborador
            colaborador={dados}
            empresas={empresas.data?.dados ?? []}
            salvando={atualizar.isPending}
            erro={atualizar.isError ? mensagemDeErroApi(atualizar.error) : undefined}
            aoSalvar={salvarDados}
            aoCancelar={() => undefined}
          />
        </ConteudoDaAba>

        <ConteudoDaAba value="vinculos">
          <SecaoVinculos
            colaborador={dados}
            cargos={cargos.data?.dados ?? []}
            departamentos={departamentos.data?.dados ?? []}
            centrosCusto={centrosCusto.data?.dados ?? []}
            unidades={unidades.data?.dados ?? []}
          />
        </ConteudoDaAba>

        <ConteudoDaAba value="contratos">
          <SecaoContratos
            colaborador={dados}
            cargos={cargos.data?.dados ?? []}
            departamentos={departamentos.data?.dados ?? []}
            centrosCusto={centrosCusto.data?.dados ?? []}
            unidades={unidades.data?.dados ?? []}
          />
        </ConteudoDaAba>

        <ConteudoDaAba value="gestores">
          <SecaoGestores colaborador={dados} colaboradores={colaboradores.data?.dados ?? []} />
        </ConteudoDaAba>

        <ConteudoDaAba value="biometria">
          <SecaoBiometria colaborador={dados} />
        </ConteudoDaAba>
      </Abas>
    </div>
  );
}
