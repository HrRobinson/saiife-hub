import coreWebVitals from 'eslint-config-next/core-web-vitals'
import typescript from 'eslint-config-next/typescript'

/**
 * Flat config. Next 16 removed `next lint`, which is what the `lint` script
 * used to call — it left the frontend with no linting at all (the binary
 * treated "lint" as a directory argument and failed). eslint and
 * eslint-config-next were already devDependencies; only the config and the
 * script were missing.
 */
const config = [
  {
    ignores: [
      '.next/**',
      'out/**',
      'node_modules/**',
      'next-env.d.ts',
      'playwright-report/**',
      'test-results/**',
      'coverage/**'
    ]
  },
  ...coreWebVitals,
  ...typescript
]

export default config
