// Syntax-check every extracted TypeScript source; fully type-check executable pairs.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(new URL('../../../node-sdk/package.json', import.meta.url));
const ts = require('typescript');
const directory = path.dirname(fileURLToPath(import.meta.url));
const testers = path.resolve(directory, '../testers');
const catalog = JSON.parse(readFileSync(path.join(testers, 'snippets.json'), 'utf8'));
const pending = new Set(Object.values(catalog).flatMap(spec => spec.blocks)
  .filter(block => block.execution_pending).map(block => path.resolve(testers, block.source)));
const configPath = path.join(directory, 'tsconfig.json');
const config = ts.readConfigFile(configPath, ts.sys.readFile);
if (config.error) throw new Error(ts.flattenDiagnosticMessageText(config.error.messageText, '\n'));
const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, directory);
const executable = parsed.fileNames.filter(name => !pending.has(path.resolve(name)));
const program = ts.createProgram(executable, parsed.options);
const diagnostics = [...parsed.errors, ...ts.getPreEmitDiagnostics(program)];
let syntaxOnly = 0;
for (const file of parsed.fileNames.filter(name => pending.has(path.resolve(name)))) {
  syntaxOnly++;
  const result = ts.transpileModule(readFileSync(file, 'utf8'), {
    fileName: file, compilerOptions: parsed.options, reportDiagnostics: true,
  });
  diagnostics.push(...(result.diagnostics || []));
}
if (diagnostics.length) {
  console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics, {
    getCanonicalFileName: name => name, getCurrentDirectory: () => directory, getNewLine: () => '\n',
  }));
  process.exitCode = 1;
} else {
  console.log(`${executable.length} executable TypeScript examples type-checked; ${syntaxOnly} legacy sources syntax-checked (type/live validation pending).`);
}
