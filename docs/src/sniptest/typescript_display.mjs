import { createRequire } from 'node:module';

const require = createRequire(new URL('../../../node-sdk/package.json', import.meta.url));
const ts = require('typescript');

export function hiddenAssignmentDeclarations(text) {
  const lines = text.split('\n');
  let offset = 0;
  let show;
  while (offset < lines.length) {
    const line = lines[offset].trim();
    if (!line) { offset++; continue; }
    const directive = line.match(/^\/\/\s*@sniptest\s+(\w+)=(.+)$/);
    if (!directive) break;
    if (directive[1] === 'show') {
      const [start, end = start] = directive[2].split('-').map(Number);
      show = [start - 1, end];
    }
    offset++;
  }
  if (!show) return [];
  const source = ts.createSourceFile('example.ts', lines.slice(offset).join('\n'), ts.ScriptTarget.Latest, true);
  const host = ts.createCompilerHost({ noLib: true });
  host.getSourceFile = name => name === 'example.ts' ? source : undefined;
  const program = ts.createProgram(['example.ts'], { noLib: true, noResolve: true }, host);
  const checker = program.getTypeChecker();
  const hidden = new Set();
  const visible = node => {
    const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line;
    return line >= show[0] && line < show[1];
  };
  const visit = node => {
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
        ts.isIdentifier(node.left) && visible(node)) {
      const declaration = checker.getSymbolAtLocation(node.left)?.valueDeclaration;
      if (declaration && ts.isVariableDeclaration(declaration) && !visible(declaration)) hidden.add(node.left.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return [...hidden].sort();
}
