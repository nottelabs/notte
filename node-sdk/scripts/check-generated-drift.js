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
];

function run(command, args, options = {}) {
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
    const source = path.join(repoRoot, repoRelativeFile);
    if (!fs.existsSync(source)) {
      continue;
    }

    const sdkRelativeFile = path.relative(sdkRelativePath, repoRelativeFile);
    copyFile(source, path.join(destinationSdkDir, sdkRelativeFile));
  }
}

function listFiles(targetPath) {
  if (!fs.existsSync(targetPath)) {
    return [];
  }

  const stat = fs.lstatSync(targetPath);
  if (stat.isFile() || stat.isSymbolicLink()) {
    return [''];
  }

  const files = [];
  const entries = fs.readdirSync(targetPath, { withFileTypes: true });
  for (const entry of entries) {
    const entryPath = path.join(targetPath, entry.name);
    if (entry.isDirectory()) {
      for (const child of listFiles(entryPath)) {
        files.push(path.join(entry.name, child));
      }
    } else if (entry.isFile() || entry.isSymbolicLink()) {
      files.push(entry.name);
    }
  }

  return files.sort();
}

function collectGeneratedDiffs(expectedSdkDir, actualSdkDir) {
  const changed = new Set();

  for (const generatedPath of GENERATED_PATHS) {
    const expectedPath = path.join(expectedSdkDir, generatedPath);
    const actualPath = path.join(actualSdkDir, generatedPath);
    const relativeFiles = new Set([...listFiles(expectedPath), ...listFiles(actualPath)]);

    for (const relativeFile of relativeFiles) {
      const displayPath = relativeFile ? path.join(generatedPath, relativeFile) : generatedPath;
      const expectedFile = relativeFile ? path.join(expectedPath, relativeFile) : expectedPath;
      const actualFile = relativeFile ? path.join(actualPath, relativeFile) : actualPath;

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

try {
  main();
} catch (err) {
  console.error('Error checking SDK status:', err.message);
  process.exit(1);
}
