"use client";

import * as React from "react";
import { Avatar as AvatarPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/** Avatar — T4. */

function Avatar({
  className,
  size = "padrao",
  ...props
}: React.ComponentProps<typeof AvatarPrimitive.Root> & { size?: "pequeno" | "padrao" | "grande" }) {
  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      data-size={size}
      className={cn(
        "group/avatar relative flex size-8 shrink-0 overflow-hidden rounded-pleno select-none",
        "data-[size=pequeno]:size-6 data-[size=grande]:size-10",
        className,
      )}
      {...props}
    />
  );
}

function AvatarImagem({ className, ...props }: React.ComponentProps<typeof AvatarPrimitive.Image>) {
  return (
    <AvatarPrimitive.Image
      data-slot="avatar-imagem"
      className={cn("aspect-square size-full", className)}
      {...props}
    />
  );
}

function AvatarContingencia({
  className,
  ...props
}: React.ComponentProps<typeof AvatarPrimitive.Fallback>) {
  return (
    <AvatarPrimitive.Fallback
      data-slot="avatar-contingencia"
      className={cn(
        "flex size-full items-center justify-center rounded-pleno bg-fundo-enfase estilo-legenda text-texto-secundario",
        className,
      )}
      {...props}
    />
  );
}

function AvatarGrupo({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="avatar-grupo"
      className={cn(
        "flex -space-x-2 *:data-[slot=avatar]:ring-2 *:data-[slot=avatar]:ring-fundo-superficie",
        className,
      )}
      {...props}
    />
  );
}

export { Avatar, AvatarImagem, AvatarContingencia, AvatarGrupo };
