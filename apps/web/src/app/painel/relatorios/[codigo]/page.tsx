import { ExecucaoDeRelatorio } from "@/componentes/paineis/relatorios";

interface PaginaProps {
  params: Promise<{ codigo: string }>;
}

export default async function PaginaDeExecucaoDeRelatorio({ params }: PaginaProps) {
  const { codigo } = await params;
  return <ExecucaoDeRelatorio codigo={codigo} />;
}
