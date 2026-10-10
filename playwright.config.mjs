import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1, // Each journey resets the shared, disposable synthetic sandbox.
  timeout: 90000,
  expect: {timeout:10000},
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  outputDir: 'test-results',
  reporter: [['list'],['html',{outputFolder:'playwright-report',open:'never'}],['json',{outputFile:'work/ui-results.json'}]],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    video: {mode:'on',size:{width:1440,height:1000}}, // Record successes at readable resolution.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {slowMo:70, ...(process.env.UI_BROWSER_PATH?{executablePath:process.env.UI_BROWSER_PATH}:{})},
  },
  projects: [
    {name:'desktop-chromium',use:{...devices['Desktop Chrome'],viewport:{width:1440,height:1000}}},
    {name:'mobile-chromium',use:{...devices['Pixel 7'],viewport:{width:412,height:915},video:{mode:'on',size:{width:412,height:915}},defaultBrowserType:'chromium'}},
  ],
  webServer: {
    command:`${process.env.UI_PYTHON || '.venv/bin/python'} -m scripts.serve_ui --port 8765 --acquisition-fixtures`,
    url:'http://127.0.0.1:8765/health',
    reuseExistingServer:false,
    timeout:180000,
  },
});
