import { Alerta, AlertaDescricao, AlertaTitulo } from "@/componentes/ui/alert";

const codigo = "rounded-pequeno bg-fundo-sutil px-1 py-0.5 font-mono text-[0.9em]";

/**
 * Regra de "cliente tolerante" (ADR-005, item 3) — o proprio ADR exige que
 * ela apareca no topo do portal, nao enterrada numa pagina interna (PCF F13,
 * T7): "a documentacao exige que o consumidor ignore campos desconhecidos e
 * nao trate enum de saida como fechado".
 */
export function AvisoClienteTolerante() {
  return (
    <Alerta variant="info" className="mb-6">
      <AlertaTitulo>Antes de integrar: seu cliente precisa ser tolerante</AlertaTitulo>
      <AlertaDescricao>
        Dentro de <code className={codigo}>/v1</code>, o contrato só evolui de forma compatível
        (ADR-005): campos novos podem aparecer em qualquer resposta e enums de saída podem ganhar
        valores novos.{" "}
        <strong>
          Seu integrador precisa ignorar campos desconhecidos e nunca tratar um enum de saída como
          fechado
        </strong>{" "}
        — sem isso, uma mudança compatível do nosso lado quebra sua integração sem aviso. Recursos
        removidos só saem depois de um ciclo de depreciação de no mínimo 180 dias, sinalizado pelos
        cabeçalhos <code className={codigo}>Deprecation</code>/
        <code className={codigo}>Sunset</code>/<code className={codigo}>Link</code>.
      </AlertaDescricao>
    </Alerta>
  );
}
