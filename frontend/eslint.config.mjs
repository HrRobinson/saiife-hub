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
  ...typescript,
  {
    rules: {
      // Downgraded to a warning on purpose, not to silence it. Linting has
      // never run in this package, so this rule surfaced six pre-existing
      // violations at once — all the same "fetch on mount, then setState"
      // idiom in billing, dashboard, verify-email, InstallsCard, PasskeyList
      // and auth-context. Fixing them means reworking how those components
      // load data, which is a deliberate change with behavioural risk, not
      // lint cleanup. Keep them visible until that work is scheduled, then
      // restore this to "error".
      'react-hooks/set-state-in-effect': 'warn'
    }
  }
]

export default config
