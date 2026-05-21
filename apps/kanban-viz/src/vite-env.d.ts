/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_COORDINATOR_URL?: string;
  readonly VITE_COORDINATOR_API_KEY?: string;
  readonly VITE_CHANGE_IDS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
