/**
 * Generate TypeScript types from the DRF Spectacular OpenAPI schema.
 *
 * This script:
 * 1. Generates an OpenAPI JSON schema via Django's `spectacular` management command.
 * 2. Feeds the schema into `openapi-typescript` to emit `src/types/api.generated.ts`.
 * 3. Prepends a `// Generated at YYYY-MM-DD ...` header (TD-278) so schema drift
 *    can be detected at code review time.
 */
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { readFileSync, writeFileSync } from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '../..');
const backendDir = path.join(repoRoot, 'backend');
const trashDir = path.join(repoRoot, '.trash');
const schemaFile = path.join(trashDir, 'schema.json');
const outputFile = path.join(repoRoot, 'frontend', 'src', 'types', 'api.generated.ts');

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: 'inherit',
      ...options,
    });
    child.on('close', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`Command failed with exit code ${code}`));
      }
    });
    child.on('error', reject);
  });
}

async function main() {
  const env = {
    ...process.env,
    PYTHONPATH: backendDir,
  };

  await run(
    'conda',
    [
      'run',
      '-n',
      'gaf',
      'python',
      path.join(backendDir, 'manage.py'),
      'spectacular',
      '--format',
      'openapi-json',
      '--file',
      schemaFile,
      '--skip-checks',
    ],
    {
      cwd: backendDir,
      env,
    },
  );

  const openapiTypescriptCli = path.join(repoRoot, 'node_modules', 'openapi-typescript', 'bin', 'cli.js');
  await run('node', [openapiTypescriptCli, schemaFile, '-o', outputFile], {
    cwd: path.join(repoRoot, 'frontend'),
  });

  // TD-278 — prepend a generation-timestamp header so reviewers can detect
  // schema drift (e.g., an api.generated.ts that is months stale relative to
  // the current OpenAPI schema). Avoid duplicating the header on re-runs.
  const today = new Date().toISOString().slice(0, 10);
  const header = `// Generated at ${today} from OpenAPI schema (run: npm run generate:api-types)\n`;
  const existing = readFileSync(outputFile, 'utf8');
  if (!existing.startsWith('// Generated at ')) {
    writeFileSync(outputFile, header + existing, 'utf8');
  } else {
    // Replace the existing header line in-place.
    const lines = existing.split('\n');
    lines[0] = header.trimEnd();
    writeFileSync(outputFile, lines.join('\n'), 'utf8');
  }

  console.log(`Generated API types at ${outputFile}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
