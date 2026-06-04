import { defineConfig } from "vitest/config";

// Minimal vitest config for frontend unit tests (buildMatrix logic, statement
// number formatter). Pure-logic tests run in the node environment; switch a
// specific test file to jsdom via a `// @vitest-environment jsdom` docblock if
// it ever needs the DOM. Project profile names vitest + tsc as the FE test tools.
export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    include: ["app/**/*.test.{ts,tsx}", "app/**/__tests__/**/*.{ts,tsx}"],
  },
});
