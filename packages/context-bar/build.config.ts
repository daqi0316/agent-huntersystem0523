import { defineBuildConfig } from "unbuild";

export default defineBuildConfig({
  entries: ["src/index"],
  declaration: true,
  sourcemap: true,
  clean: true,
  rollup: {
    emitCJS: true,
    esbuild: {
      target: "es2020",
      jsx: "automatic",
    },
  },
  externals: [
    "react",
    "react-dom",
    "react/jsx-runtime",
    "zustand",
    "next",
    "next/navigation",
    "next/link",
    "lucide-react",
    "clsx",
    "tailwind-merge",
    "sonner",
    "@ai-recruitment/agent-store",
  ],
});
