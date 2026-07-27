import type { Metadata } from "next";
import Link from "next/link";

import { Cartao, CartaoCabecalho, CartaoDescricao, CartaoTitulo } from "@/componentes/ui/card";

export const metadata: Metadata = { title: "Cadastros" };

const SECOES = [
  {
    href: "/painel/cadastros/empresas",
    titulo: "Empresas",
    descricao: "Matriz, filiais, dados fiscais.",
  },
  {
    href: "/painel/cadastros/unidades",
    titulo: "Unidades",
    descricao: "Locais de trabalho, geocerca e redes permitidas.",
  },
  {
    href: "/painel/cadastros/departamentos",
    titulo: "Departamentos",
    descricao: "Estrutura departamental.",
  },
  {
    href: "/painel/cadastros/centros-custo",
    titulo: "Centros de custo",
    descricao: "Apropriação de horas.",
  },
  { href: "/painel/cadastros/cargos", titulo: "Cargos", descricao: "Cargos e CBO." },
  {
    href: "/painel/cadastros/equipes",
    titulo: "Equipes",
    descricao: "Agrupamento operacional e escala.",
  },
  {
    href: "/painel/cadastros/colaboradores",
    titulo: "Colaboradores",
    descricao: "Pessoas, contratos, vínculos, biometria.",
  },
  {
    href: "/painel/cadastros/dispositivos",
    titulo: "Dispositivos",
    descricao: "Aparelhos que podem originar marcação.",
  },
];

/** Índice de navegação das telas de cadastro (T4–T8) — não é rota fixada pelo PCF, acrescentada para navegabilidade dentro do ownership de A2. */
export default function PaginaIndiceDeCadastros() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="estilo-titulo-pagina text-texto-primario">Cadastros</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SECOES.map((secao) => (
          <Link key={secao.href} href={secao.href}>
            <Cartao className="h-full transition-colors hover:border-borda-forte">
              <CartaoCabecalho>
                <CartaoTitulo>{secao.titulo}</CartaoTitulo>
                <CartaoDescricao>{secao.descricao}</CartaoDescricao>
              </CartaoCabecalho>
            </Cartao>
          </Link>
        ))}
      </div>
    </div>
  );
}
