import { defineBuildConfig } from "unbuild";

export default defineBuildConfig({
  entries: ["src/index", "src/parser", "src/tool-labels"],
  declaration: true,
  sourcemap: true,
  clean: true,
  rollup: {
    emitCJS: true,
    esbuild: {
      target: "es2020",
    },
  },
  externals: ["react", "react-dom", "zustand"],
});
