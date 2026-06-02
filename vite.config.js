import { defineConfig } from "vite";

// StackBlitz/WebContainer 에서 바로 뜨도록 host 노출, 포트 고정 해제.
export default defineConfig({
  server: { host: true, strictPort: false },
  preview: { host: true },
});
