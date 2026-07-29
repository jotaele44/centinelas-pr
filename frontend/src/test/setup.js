// Rendered from thehub-pr/federation-templates/baseline/test-setup.js.
// Do not hand-edit — template-drift.yml fails the build if you do.
import '@testing-library/jest-dom/vitest';
import * as matchers from 'vitest-axe/matchers';
import { expect } from 'vitest';

expect.extend(matchers);
