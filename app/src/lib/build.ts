/** Injected by Vite at build time; see gitInfo() in vite.config.ts. */
declare const __BUILD__: {
  sha: string
  short: string
  branch: string
  /** True when built from a working tree with uncommitted changes. */
  dirty: boolean
  builtAt: string
}

export const BUILD = __BUILD__
