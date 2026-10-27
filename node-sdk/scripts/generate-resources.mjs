import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Shared public naming contract; Python converts these names to snake_case.
const naming = JSON.parse(fs.readFileSync(path.join(root, '../openapi/resources.json'), 'utf8'));
const groups = [...new Set(Object.values(naming).filter(entry => !entry.exclude).map(entry => entry.resource))];
const camel = value => value.replace(/^_+/, "").replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
const byOperation = new Map(Object.entries(naming).map(([id, entry]) => [entry.nodeOperation ?? camel(id), entry]));
export function checkCoverage(spec) {
  const ids = new Set(Object.values(spec.paths).flatMap(item => Object.entries(item)
    .filter(([method]) => ['get', 'post', 'put', 'patch', 'delete'].includes(method))
    .map(([, operation]) => operation.operationId)));
  for (const id of ids) if (!naming[id]) throw new Error(`Unmapped operation: ${id}`);
  for (const id of Object.keys(naming)) if (!ids.has(id)) throw new Error(`Stale operation mapping: ${id}`);
}

/** Read the generated AST, not a second endpoint/schema registry. */
export function generateResources(sdkSource, typesSource, registry = byOperation) {
  const parse = (name, source) => ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true);
  const sdk = parse('sdk.gen.ts', sdkSource);
  const types = parse('types.gen.ts', typesSource);
  const definitions = new Map(types.statements.filter(ts.isTypeAliasDeclaration).map(node => [node.name.text, node.type]));
  const output = new Map(groups.map(group => [group, new Map()]));
  for (const statement of sdk.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || !declaration.initializer || !ts.isArrowFunction(declaration.initializer)) continue;
      const operation = declaration.name.text;
      const parameter = declaration.initializer.parameters[0];
      const data = parameter?.type?.typeArguments?.[0]?.getText(sdk);
      const definition = definitions.get(data);
      if (!data) continue;
      if (!definition || !ts.isTypeLiteralNode(definition)) throw new Error(`Missing operation data: ${operation}`);
      const members = new Map(definition.members.map(member => [member.name?.getText(types).replace(/^['"]|['"]$/g, ''), member]));
      const url = members.get('url')?.type;
      if (!url || !ts.isLiteralTypeNode(url) || !ts.isStringLiteral(url.literal)) continue;
      const entry = registry.get(operation);
      if (!entry) throw new Error(`Unmapped operation: ${operation}`);
      if (entry.exclude) continue;
      const { resource: group, method } = entry;
      if (!/^[a-zA-Z_$][\w$]*$/.test(method)) throw new Error(`Invalid resource method: ${operation}`);
      if (output.get(group).has(method)) throw new Error(`Resource method collision: ${group}.${method}`);
      const args = [];
      const request = ['client', 'throwOnError: true', 'signal: requestOptions.signal'];
      if (entry.nodeParseAs) request.push(`parseAs: ${JSON.stringify(entry.nodeParseAs)}`);
      const headers = members.get('headers');
      let requestOptions = 'ResourceRequestOptions';
      let requiredHeaders = false;
      if (headers?.type && headers.type.kind !== ts.SyntaxKind.NeverKeyword) {
        if (!ts.isTypeLiteralNode(headers.type)) throw new Error(`Unsupported headers: ${operation}`);
        const headerName = member => member.name.getText(types).replace(/^['"]|['"]$/g, '');
        const bound = headers.type.members.some(member => headerName(member) === 'x-notte-api-key');
        const supplied = headers.type.members.filter(member => headerName(member) !== 'x-notte-api-key');
        requiredHeaders = !headers.questionToken && supplied.some(member => !member.questionToken);
        if (supplied.length) {
          requestOptions += ` & { headers${requiredHeaders ? '' : '?'}: Omit<NonNullable<Types.${data}['headers']>, 'x-notte-api-key'> }`;
        }
        const values = [supplied.length ? '...requestOptions.headers' : '', bound ? "'x-notte-api-key': getApiKey()" : ''].filter(Boolean);
        if (values.length) request.push(`headers: { ${values.join(', ')} }`);
      }
      const pathMember = members.get('path');
      if (pathMember?.type && pathMember.type.kind !== ts.SyntaxKind.NeverKeyword) {
        if (!ts.isTypeLiteralNode(pathMember.type)) throw new Error(`Unsupported path shape: ${operation}`);
        const keys = [...url.literal.text.matchAll(/\{([^}]+)\}/g)].map(match => match[1]);
        if (keys.length !== pathMember.type.members.length) throw new Error(`Path mismatch: ${operation}`);
        const names = keys.map(camel);
        if (new Set(names).size !== names.length || names.some(name =>
          !/^[a-zA-Z_$][\w$]*$/.test(name) || ['client', 'getApiKey', 'body', 'query', 'requestOptions', '__proto__'].includes(name)
        )) throw new Error(`Unsafe path parameter names: ${operation}`);
        for (const key of keys) args.push(`${camel(key)}: Types.${data}['path'][${JSON.stringify(key)}]`);
        request.push(`path: { ${keys.map(key => `${JSON.stringify(key)}: ${camel(key)}`).join(', ')} }`);
      }
      // These operations originally had no query. Keep existing request-options
      // positions and append their new query parameters.
      const queryAfterOptions = ['functionRunGetMetadata', 'functionRuntimeHealth'].includes(operation);
      let trailingQuery;
      for (const field of ['body', 'query']) {
        const member = members.get(field);
        if (!member?.type || member.type.kind === ts.SyntaxKind.NeverKeyword) continue;
        const optional = Boolean(member.questionToken);
        // Use an optional default only when no required parameter follows it.
        const laterRequired = field === 'body' && members.get('query')?.type?.kind !== ts.SyntaxKind.NeverKeyword
          && members.has('query') && !members.get('query').questionToken;
        const argument = `${field}: Types.${data}['${field}']${optional && !laterRequired ? ' = undefined' : ''}`;
        if (field === 'query' && queryAfterOptions) trailingQuery = argument;
        else args.push(argument);
        request.push(field);
      }
      args.push(`requestOptions: ${requestOptions}${requiredHeaders ? '' : ' = {}'}`);
      if (trailingQuery) args.push(trailingQuery);
      const comment = `    /** ${operation}: ${url.literal.text.replaceAll('*/', '* /')}. Returns the API response body. */`;
      const normalize = operation === 'sessionStart'
        ? '\n      body = { ...body };\n      if (body.record_session === true) delete body.record_session;\n      if (body.log_session === true) delete body.log_session;'
        : '';
      output.get(group).set(method, `${comment}\n    ${method}: async (${args.join(', ')}) => {${normalize}\n      const response = await operations.${operation}({ ${request.join(', ')} });\n      return response.data;\n    },`);
      for (const alias of entry.aliases ?? []) {
        if (!/^[a-zA-Z_$][\w$]*$/.test(alias.method)) throw new Error(`Invalid resource alias: ${operation}`);
        if (!output.has(alias.resource)) throw new Error(`Unknown alias resource: ${alias.resource}`);
        if (output.get(alias.resource).has(alias.method)) throw new Error(`Resource method collision: ${alias.resource}.${alias.method}`);
        const source = output.get(group).get(method).replace(`    ${method}: async`, `    ${alias.method}: async`);
        output.get(alias.resource).set(alias.method, source);
      }
    }
  }
  if (![...output.values()].some(methods => methods.size)) throw new Error('No resource operations found');
  return `// Auto-generated by scripts/generate-resources.mjs. Do not edit.\nimport type { Client } from './lib/client/client';\nimport type * as Types from './lib/client/types.gen';\nimport * as operations from './lib/client/sdk.gen';\n\n/** Per-request cancellation; authentication and transport stay bound to NotteClient. */\nexport interface ResourceRequestOptions { signal?: AbortSignal }\n\n/** Low-level API resources. Lifecycle helpers remain on Session/Function. */\nexport function createResources(client: Client, getApiKey: () => string) {\n  return {\n${[...output].map(([group, methods]) => `  ${group}: {\n${[...methods].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, source]) => source).join('\n')}\n  },`).join('\n')}\n  };\n}\n`;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  checkCoverage(JSON.parse(fs.readFileSync(path.join(root, '../openapi/openapi.json'), 'utf8')));
  const content = generateResources(fs.readFileSync(path.join(root, 'src/lib/client/sdk.gen.ts'), 'utf8'), fs.readFileSync(path.join(root, 'src/lib/client/types.gen.ts'), 'utf8'));
  const target = path.join(root, 'src/resources.gen.ts');
  if (process.argv.includes('--check')) {
    if (!fs.existsSync(target) || fs.readFileSync(target, 'utf8') !== content) {
      console.error('Generated resources are stale. Run npm run resources:generate.');
      process.exitCode = 1;
    }
  } else fs.writeFileSync(target, content);
}
