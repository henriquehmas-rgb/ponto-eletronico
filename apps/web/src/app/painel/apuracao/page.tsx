import type { Metadata } from "next";

import { GradeDeApuracao } from "@/componentes/paineis/apuracao/grade-de-apuracao";

export const metadata: Metadata = { title: "Apuração" };

export default function PaginaDeApuracao() {
  return <GradeDeApuracao />;
}
