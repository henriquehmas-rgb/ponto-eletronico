import { DetalheWebhook } from "@/componentes/paineis/integracoes";

interface PaginaProps {
  params: Promise<{ webhookId: string }>;
}

export default async function PaginaDeDetalheDeWebhook({ params }: PaginaProps) {
  const { webhookId } = await params;
  return <DetalheWebhook webhookId={webhookId} />;
}
