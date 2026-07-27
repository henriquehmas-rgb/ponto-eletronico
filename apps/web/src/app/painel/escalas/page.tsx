import type { Metadata } from "next";

import { GradeVisualDeEscala } from "@/componentes/paineis/escalas/grade-visual";

export const metadata: Metadata = { title: "Grade de escala" };

export default function PaginaDeGradeDeEscala() {
  return <GradeVisualDeEscala />;
}
