import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Junta classes do Tailwind resolvendo conflitos (a ultima vence).
 * Assinatura exigida pelo shadcn/ui — ver `components.json` (`utils`).
 */
export function cn(...entradas: ClassValue[]): string {
  return twMerge(clsx(entradas));
}
