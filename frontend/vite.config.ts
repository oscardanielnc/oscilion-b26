import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base relativa para que el build sirva bien montado en "/" por FastAPI
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
});
