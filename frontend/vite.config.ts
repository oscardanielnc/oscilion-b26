import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// relative base so the build works when FastAPI mounts it at "/"
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
});
