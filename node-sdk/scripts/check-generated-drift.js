#!/usr/bin/env node

/**
 * Checks whether the checked-in SDK output matches the staging OpenAPI spec.
 *
 * The check regenerates the SDK in a temporary directory and compares the
 * generated files, instead of comparing an OpenAPI hash. This avoids release
 * failures when the raw spec changes in a way that does not affect generated
 * SDK output.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const SDK_DIR = path.resolve(__dirname, '..');
const GENERATED_PATHS = [
  'src/lib/client',
  'src/proxy/patterns.ts',
  'src/resources.gen.ts',
];
// The only programs this script shells out to.
const ALLOWED_COMMANDS = new Set(['git', 'npm']);

function run(command, args, options = {}) {
  if (!ALLOWED_COMMANDS.has(command)) {
    throw new Error(`Refusing to run unexpected command: ${command}`);
  }

  // nosemgrep: javascript.lang.security.detect-child-process.detect-child-process -- command is allowlisted above
  const result = spawnSync(command, args, {
    cwd: options.cwd || SDK_DIR,
    env: process.env,
    encoding: 'utf8',
    stdio: options.stdio || 'pipe',
  });

  if (result.status !== 0) {
    const output = [result.stdout, result.stderr].filter(Boolean).join('\n').trim();
    throw new Error(`${command} ${args.join(' ')} failed${output ? `\n${output}` : ''}`);
  }

  return typeof result.stdout === 'string' ? result.stdout.trim() : '';
}

function runIn(cwd, command, args, options = {}) {
  return run(command, args, { cwd, ...options });
}

// Resolves segments under baseDir and refuses any result that escapes it.
// Segments come from `git ls-files` and directory listings, never from users,
// so this is a guard against a malformed path rather than an expected failure.
function resolveInside(baseDir, ...segments) {
  // nosemgrep: javascript.lang.security.audit.path-traversal.path-join-resolve-traversal.path-join-resolve-traversal -- checked below
  const resolved = path.resolve(baseDir, ...segments);
  const relative = path.relative(baseDir, resolved);
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Path escapes ${baseDir}: ${segments.join('/')}`);
  }
  return resolved;
}

function copyFile(source, destination) {
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(source, destination);
}

function copyTrackedSdkFiles(destinationSdkDir) {
  const repoRoot = run('git', ['rev-parse', '--show-toplevel']);
  const sdkRelativePath = path.relative(repoRoot, SDK_DIR);
  const trackedFiles = runIn(repoRoot, 'git', ['ls-files', '-z', '--', sdkRelativePath])
    .split('\0')
    .filter(Boolean);

  for (const repoRelativeFile of trackedFiles) {
    const source = resolveInside(repoRoot, repoRelativeFile);
    if (!fs.existsSync(source)) {
      continue;
    }

    const sdkRelativeFile = path.relative(sdkRelativePath, repoRelativeFile);
    copyFile(source, resolveInside(destinationSdkDir, sdkRelativeFile));
  }
}

// Lists files under targetPath, relative to rootPath. A file root yields ['']
// (the root itself).
function listFiles(rootPath, targetPath = rootPath) {
  if (!fs.existsSync(targetPath)) {
    return [];
  }

  const stat = fs.lstatSync(targetPath);
  if (stat.isFile() || stat.isSymbolicLink()) {
    return [path.relative(rootPath, targetPath)];
  }

  const files = [];
  const entries = fs.readdirSync(targetPath, { withFileTypes: true });
  for (const entry of entries) {
    const entryPath = resolveInside(targetPath, entry.name);
    if (entry.isDirectory()) {
      files.push(...listFiles(rootPath, entryPath));
    } else if (entry.isFile() || entry.isSymbolicLink()) {
      files.push(path.relative(rootPath, entryPath));
    }
  }

  return files.sort();
}

function collectGeneratedDiffs(expectedSdkDir, actualSdkDir) {
  const changed = new Set();

  for (const generatedPath of GENERATED_PATHS) {
    const expectedPath = resolveInside(expectedSdkDir, generatedPath);
    const actualPath = resolveInside(actualSdkDir, generatedPath);
    const relativeFiles = new Set([...listFiles(expectedPath), ...listFiles(actualPath)]);

    for (const relativeFile of relativeFiles) {
      const expectedFile = resolveInside(expectedPath, relativeFile);
      const actualFile = resolveInside(actualPath, relativeFile);
      const displayPath = path.relative(expectedSdkDir, expectedFile);

      if (!fs.existsSync(expectedFile) || !fs.existsSync(actualFile)) {
        changed.add(displayPath);
        continue;
      }

      const expected = readComparableContent(expectedFile);
      const actual = readComparableContent(actualFile);
      if (!expected.equals(actual)) {
        changed.add(displayPath);
      }
    }
  }

  return [...changed].sort();
}

function readComparableContent(filePath) {
  const stat = fs.lstatSync(filePath);
  if (stat.isSymbolicLink()) {
    return Buffer.from(`symlink:${fs.readlinkSync(filePath)}`);
  }

  return fs.readFileSync(filePath);
}

function main() {
  const sourceNodeModules = path.join(SDK_DIR, 'node_modules');

  if (!fs.existsSync(sourceNodeModules)) {
    throw new Error('node_modules is missing. Run `npm ci` in node-sdk before checking SDK drift.');
  }

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'notte-node-sdk-check-'));
  const tempSdkDir = path.join(tempRoot, 'node-sdk');

  try {
    copyTrackedSdkFiles(tempSdkDir);
    fs.symlinkSync(sourceNodeModules, path.join(tempSdkDir, 'node_modules'), 'dir');

    console.log('Regenerating SDK from https://us-staging.notte.cc/openapi.json in a temporary directory...');
    runIn(tempSdkDir, 'npm', ['run', 'generate:staging'], { stdio: 'inherit' });

    const changedFiles = collectGeneratedDiffs(SDK_DIR, tempSdkDir);
    if (changedFiles.length === 0) {
      console.log('\nGenerated SDK output is up to date with staging');
      return;
    }

    console.error('\nSDK is OUTDATED - generated output differs from staging.');
    console.error('   Changed generated files:');
    for (const file of changedFiles) {
      console.error(`   - ${file}`);
    }
    console.error('\n   Run `npm run generate:staging` and commit the generated changes.');

    process.exitCode = 1;
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

module.exports = { collectGeneratedDiffs, listFiles, resolveInside, run };

if (require.main === module) {
  try {
    main();
  } catch (err) {
    console.error('Error checking SDK status:', err.message);
    process.exit(1);
  }
}
