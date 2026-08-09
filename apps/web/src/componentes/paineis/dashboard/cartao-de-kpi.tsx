import { Cartao, CartaoConteudo } from "@/componentes/ui/card";
import { Esqueleto } from "@/componentes/ui/skeleton";

export interface CartaoDeKpiProps {
  rotulo: string;
  valor: string;
  // `| undefined` explícito: sob `exactOptionalPropertyTypes`, permite que os
  // chamadores (que calculam `descricao` condicionalmente) passem `undefined`
  // sem ficção de tipos.
  descricao?: string | undefined;
  carregando?: boolean;
}

/**
 * Cartão de indicador numérico único — bloco básico dos KPIs do dashboard (T2).
 * Visual: catálogo #5 de `docs/design-system-oficial.md` (tile de KPI,
 * cartão flutuante padrão).
 */
export function CartaoDeKpi({ rotulo, valor, descricao, carregando = false }: CartaoDeKpiProps) {
  return (
    <Cartao className="rounded-suave shadow-flutuante-cartao">
      <CartaoConteudo className="flex flex-col gap-1">
        <p className="estilo-legenda uppercase text-texto-terciario">{rotulo}</p>
        {carregando ? (
          <Esqueleto className="h-8 w-20" />
        ) : (
          <p className="estilo-numero-destaque text-texto-primario">{valor}</p>
        )}
        {descricao ? <p className="estilo-legenda text-texto-secundario">{descricao}</p> : null}
      </CartaoConteudo>
    </Cartao>
  );
}
