// Browser tests against a running firecal API that serves the built frontend (scripts/check.sh starts
// one on the sample data and one on the full data). FIRECAL_URL points at it.
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
	testDir: 'e2e',
	timeout: 30_000,
	expect: { timeout: 10_000 },
	fullyParallel: true,
	workers: 4,
	reporter: [['list']],
	outputDir: 'test-results',
	use: {
		baseURL: process.env.FIRECAL_URL ?? 'http://127.0.0.1:8090',
		trace: 'retain-on-failure'
	},
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]
});
