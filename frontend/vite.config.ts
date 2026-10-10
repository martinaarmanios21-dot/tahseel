// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
    // Static SPA build so the Tahseel Python server can serve it (no Node/Cloudflare runtime needed).
    spa: { enabled: true, prerender: { outputPath: "/index.html" } },
    // The earlier role-based screens ran on simulator data only. They stay in the repo (owner's work) but are no
    // longer routed or bundled: the app now runs exclusively on the user's imported invoices.
    router: {
    },
  },
});
