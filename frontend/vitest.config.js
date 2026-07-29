import path from 'node:path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Rendered from thehub-pr/federation-templates/baseline/vitest.config.js.
// Do not hand-edit — template-drift.yml fails the build if you do.
//
// Deliberately separate from vite.config.js rather than merging it: the build
// config carries offline-export plumbing (vite-plugin-singlefile) and federation
// design aliases that a test run neither needs nor should depend on.
//
// Tests are co-located with the code they cover (src/**/*.test.{js,jsx}) rather
// than living in a tests/ directory, matching thehub-pr. Note the shared eslint
// config lints src/components/** and src/pages/**, so co-located test files are
// linted too — import describe/it/expect from 'vitest' explicitly rather than
// relying on `globals: true`, or the lint gate will flag them as undefined.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
    include: ['src/**/*.test.{js,jsx}'],
  },
});
