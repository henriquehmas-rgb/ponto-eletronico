import * as React from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/** Alerta (`alert`) — T4. Mesma regra do Selo: icone obrigatorio, cor nunca sozinha. */

const ICONE_POR_VARIANTE = {
  neutro: Info,
  sucesso: CheckCircle2,
  atencao: AlertTriangle,
  erro: XCircle,
  info: Info,
} as const;

const alertVariants = cva(
  "relative grid w-full grid-cols-[auto_1fr] items-start gap-x-3 gap-y-1 rounded-medio border p-4 estilo-corpo [&>svg]:size-5 [&>svg]:translate-y-0.5",
  {
    variants: {
      variant: {
        neutro: "border-borda-padrao bg-fundo-superficie text-texto-primario [&>svg]:text-texto-terciario",
        sucesso: "border-estado-sucesso-borda bg-estado-sucesso-fundo text-estado-sucesso-texto [&>svg]:text-estado-sucesso-icone",
        atencao: "border-estado-atencao-borda bg-estado-atencao-fundo text-estado-atencao-texto [&>svg]:text-estado-atencao-icone",
        erro: "border-estado-erro-borda bg-estado-erro-fundo text-estado-erro-texto [&>svg]:text-estado-erro-icone",
        info: "border-estado-info-borda bg-estado-info-fundo text-estado-info-texto [&>svg]:text-estado-info-icone",
      },
    },
    defaultVariants: {
      variant: "neutro",
    },
  },
);

interface AlertaProps extends React.ComponentProps<"div">, VariantProps<typeof alertVariants> {}

function Alerta({ className, variant = "neutro", children, ...props }: AlertaProps) {
  const Icone = ICONE_POR_VARIANTE[variant ?? "neutro"];
  return (
    <div data-slot="alerta" role="alert" className={cn(alertVariants({ variant }), className)} {...props}>
      <Icone aria-hidden="true" />
      <div className="col-start-2 grid gap-1">{children}</div>
    </div>
  );
}

function AlertaTitulo({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="alerta-titulo" className={cn("estilo-rotulo", className)} {...props} />;
}

function AlertaDescricao({ className, ...props }: React.ComponentProps<"div">) {
  // Sem cor propria: herda `text-estado-<variante>-texto` do <Alerta> pai,
  // que e o par contra `estado.<variante>Fundo` MEDIDO no contrato (>= 4.5:1).
  // Uma cor "secundaria" gasta aqui poderia cair fora do par verificado.
  return <div data-slot="alerta-descricao" className={cn("estilo-legenda", className)} {...props} />;
}

export { Alerta, AlertaTitulo, AlertaDescricao };
