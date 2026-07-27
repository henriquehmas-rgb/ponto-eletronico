/**
 * Tipos do módulo de sessão (T1).
 *
 * Estes tipos são o CONTRATO exato descrito em `docs/fases/F08-web-colaborador-webcam.md`
 * §2: a F9b (fase irmã, mesma onda) importa `ProvedorDeSessao`/`useSessao` daqui
 * sem recriar sessão própria. Não mude a forma sem avisar quem consome.
 *
 * Deliberadamente MENOR que `SessaoAtual` do contrato (`packages/contracts/openapi.yaml`):
 * não inclui `permissoes`/`perfis` — isso é RBAC granular, que a F9b resolve
 * com sua própria chamada a `obterSessaoAtual` por cima de `autenticado`.
 */

export interface UsuarioAutenticado {
  id: string;
  nome: string;
  email: string;
}

export interface TenantResumido {
  slug: string;
  nomeExibicao: string;
}

export interface CredenciaisDeEntrada {
  email: string;
  senha: string;
  /** Slug do tenant. Dispensável quando o acesso é resolvido por subdomínio. */
  tenant?: string;
}

/** Resposta de `POST /api/auth/login` (ou `/api/auth/mfa/verificar`) quando a autenticação foi concluída. */
export interface RespostaDeAutenticacao {
  mfaRequerido: false;
  accessToken: string;
  expiresIn: number;
  usuario: UsuarioAutenticado;
  tenant: TenantResumido;
}

/** Resposta quando falta validar o segundo fator — nenhum token foi emitido ainda. */
export interface RespostaDeMfaRequerido {
  mfaRequerido: true;
  desafioId: string;
  metodosMfa: string[];
}

export type RespostaDeLogin = RespostaDeAutenticacao | RespostaDeMfaRequerido;
