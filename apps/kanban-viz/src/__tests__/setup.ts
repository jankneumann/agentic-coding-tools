// The /vitest entry point, not the bare package. jest-dom v6 augments
// vitest's own `Assertion` interface only through this path; under vitest 3
// the bare import happened to reach the same declarations, and under
// vitest 5 it does not — the matchers still work at runtime, but `tsc`
// stops seeing `toBeInTheDocument` and friends.
import "@testing-library/jest-dom/vitest";
