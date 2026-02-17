#!/usr/bin/env npx ts-node
/**
 * TypeScript Codebase Analyzer
 *
 * Extracts component hierarchies, hook usage, import graphs, API client call
 * sites, and function metadata from a TypeScript/TSX project using ts-morph.
 *
 * Required dependencies (install before running):
 *   npm install ts-morph typescript
 *
 * Usage:
 *   npx ts-node scripts/analyze_typescript.ts <directory> \
 *     [--tsconfig tsconfig.json] \
 *     [--output docs/architecture-analysis/ts_analysis.json]
 */

import * as path from "path";
import * as fs from "fs";
import {
  Project,
  SourceFile,
  SyntaxKind,
  Node,
  FunctionDeclaration,
  VariableDeclaration,
  ArrowFunction,
  FunctionExpression,
  ClassDeclaration,
  CallExpression,
  JsxOpeningElement,
  JsxSelfClosingElement,
  PropertyAccessExpression,
  ParameterDeclaration,
  ts,
} from "ts-morph";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ImportInfo {
  source: string;
  specifiers: string[];
  is_internal: boolean;
}

interface ExportInfo {
  name: string;
  kind: string; // "function" | "class" | "variable" | "type" | "interface" | "default"
}

interface ModuleInfo {
  name: string;
  file: string;
  imports: ImportInfo[];
  exports: ExportInfo[];
}

interface ParameterInfo {
  name: string;
  type: string;
  is_optional: boolean;
}

interface FunctionInfo {
  name: string;
  qualified_name: string;
  file: string;
  line_start: number;
  line_end: number;
  is_async: boolean;
  is_exported: boolean;
  parameters: ParameterInfo[];
}

interface ApiCallInfo {
  url: string;
  method: string;
}

interface ComponentInfo {
  name: string;
  file: string;
  line_start: number;
  line_end: number;
  hooks: string[];
  children: string[];
  props: string[];
  is_exported: boolean;
  api_calls: ApiCallInfo[];
}

interface CustomHookInfo {
  name: string;
  file: string;
  hooks_used: string[];
}

interface ImportGraphEdge {
  from: string;
  to: string;
}

interface ApiCallSiteInfo {
  component_or_function: string;
  url: string;
  method: string;
  file: string;
  line: number;
}

interface SummaryInfo {
  total_modules: number;
  total_components: number;
  total_functions: number;
  total_custom_hooks: number;
  top_components: string[];
  complex_components: string[];
}

interface AnalysisResult {
  modules: ModuleInfo[];
  functions: FunctionInfo[];
  components: ComponentInfo[];
  custom_hooks: CustomHookInfo[];
  import_graph: ImportGraphEdge[];
  api_call_sites: ApiCallSiteInfo[];
  summary: SummaryInfo;
}

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------

interface CliArgs {
  directory: string;
  tsconfig: string | undefined;
  output: string;
}

function parseArgs(): CliArgs {
  const args = process.argv.slice(2);
  let directory: string | undefined;
  let tsconfig: string | undefined;
  let output = "docs/architecture-analysis/ts_analysis.json";

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--tsconfig" && i + 1 < args.length) {
      tsconfig = args[++i];
    } else if (arg === "--output" && i + 1 < args.length) {
      output = args[++i];
    } else if (arg === "--help" || arg === "-h") {
      console.log(
        "Usage: npx ts-node scripts/analyze_typescript.ts <directory> [--tsconfig tsconfig.json] [--output docs/architecture-analysis/ts_analysis.json]"
      );
      process.exit(0);
    } else if (!directory && !arg.startsWith("--")) {
      directory = arg;
    }
  }

  if (!directory) {
    console.error("Error: <directory> argument is required.");
    console.log(
      "Usage: npx ts-node scripts/analyze_typescript.ts <directory> [--tsconfig tsconfig.json] [--output docs/architecture-analysis/ts_analysis.json]"
    );
    process.exit(1);
  }

  return {
    directory: path.resolve(directory),
    tsconfig: tsconfig ? path.resolve(tsconfig) : undefined,
    output: path.resolve(output),
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns true for PascalCase identifiers (first char uppercase). */
function isPascalCase(name: string): boolean {
  return /^[A-Z][a-zA-Z0-9]*$/.test(name);
}

/** Returns true if the name looks like a React hook (starts with `use`). */
function isHookName(name: string): boolean {
  return /^use[A-Z]/.test(name);
}

/** Determine whether an import path is internal (relative). */
function isInternalImport(source: string): boolean {
  return source.startsWith(".");
}

/** Resolve a relative import to a normalised path key (no extension). */
function resolveImportPath(
  fromFile: string,
  importSource: string
): string {
  const dir = path.dirname(fromFile);
  const resolved = path.resolve(dir, importSource);
  // Strip common extensions for graph consistency
  return resolved.replace(/\.(tsx?|jsx?|mjs|cjs)$/, "");
}

/** Normalise a file path to a short key (relative to project root). */
function fileKey(filePath: string, root: string): string {
  return path.relative(root, filePath);
}

/** Check if a file should be skipped. */
function shouldSkipFile(filePath: string): boolean {
  const parts = filePath.split(path.sep);
  if (parts.includes("node_modules")) return true;
  const base = path.basename(filePath);
  if (base.includes(".test.") || base.includes(".spec.")) return true;
  return false;
}

/** Extract parameter info from a parameter declaration. */
function extractParameter(param: ParameterDeclaration): ParameterInfo {
  return {
    name: param.getName(),
    type: param.getType().getText(param) || "unknown",
    is_optional: param.isOptional(),
  };
}

/** Check whether a node is exported from its source file. */
function isNodeExported(node: Node): boolean {
  // Direct export keyword
  if (Node.isExportable(node) && node.isExported()) return true;

  // Variable statement: check the parent variable statement
  const parent = node.getParent();
  if (Node.isVariableDeclaration(node)) {
    const varStatement = node.getFirstAncestorByKind(
      SyntaxKind.VariableStatement
    );
    if (varStatement && varStatement.isExported()) return true;
  }
  if (parent && Node.isVariableDeclarationList(parent)) {
    const varStatement = parent.getParent();
    if (varStatement && Node.isVariableStatement(varStatement)) {
      if (varStatement.isExported()) return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// API call detection helpers
// ---------------------------------------------------------------------------

interface RawApiCall {
  url: string;
  method: string;
  line: number;
}

const AXIOS_METHODS = new Set([
  "get",
  "post",
  "put",
  "patch",
  "delete",
  "head",
  "options",
  "request",
]);

const GRAPHQL_IDENTIFIERS = new Set([
  "query",
  "mutate",
  "subscribe",
  "request",
  "rawRequest",
  "useQuery",
  "useMutation",
  "useLazyQuery",
  "useSubscription",
]);

function extractApiCalls(body: Node): RawApiCall[] {
  const calls: RawApiCall[] = [];
  const callExpressions = body.getDescendantsOfKind(
    SyntaxKind.CallExpression
  );

  for (const call of callExpressions) {
    const expr = call.getExpression();
    const argsNodes = call.getArguments();

    // --- fetch("url") or fetch("url", { method }) ---
    if (Node.isIdentifier(expr) && expr.getText() === "fetch") {
      const urlArg = argsNodes[0];
      const url = extractStringValue(urlArg);
      let method = "GET";
      // Look for { method: "..." } in the second argument
      if (argsNodes.length >= 2) {
        const optionsArg = argsNodes[1];
        method = extractMethodFromOptions(optionsArg) || "GET";
      }
      calls.push({ url: url || "<dynamic>", method, line: call.getStartLineNumber() });
      continue;
    }

    // --- axios.get/post/etc or apiClient.get/post/etc ---
    if (Node.isPropertyAccessExpression(expr)) {
      const methodName = expr.getName();
      if (AXIOS_METHODS.has(methodName)) {
        const urlArg = argsNodes[0];
        const url = extractStringValue(urlArg);
        calls.push({
          url: url || "<dynamic>",
          method: methodName.toUpperCase() === "REQUEST" ? extractMethodFromOptions(argsNodes[0]) || "GET" : methodName.toUpperCase(),
          line: call.getStartLineNumber(),
        });
        continue;
      }

      // GraphQL client calls: client.query(...), client.mutate(...)
      if (GRAPHQL_IDENTIFIERS.has(methodName)) {
        calls.push({
          url: "<graphql>",
          method: methodName.toUpperCase(),
          line: call.getStartLineNumber(),
        });
        continue;
      }
    }

    // --- Typed API client methods: e.g. api.getUsers(), api.createPost(...)
    // Heuristic: property access on an identifier ending in "api", "client", "service"
    if (Node.isPropertyAccessExpression(expr)) {
      const objectExpr = expr.getExpression();
      if (Node.isIdentifier(objectExpr)) {
        const objName = objectExpr.getText().toLowerCase();
        if (
          objName.endsWith("api") ||
          objName.endsWith("client") ||
          objName.endsWith("service")
        ) {
          const methodName = expr.getName();
          // Skip if already handled as axios method or graphql
          if (!AXIOS_METHODS.has(methodName) && !GRAPHQL_IDENTIFIERS.has(methodName)) {
            const inferredMethod = inferHttpMethod(methodName);
            calls.push({
              url: `<${objectExpr.getText()}.${methodName}>`,
              method: inferredMethod,
              line: call.getStartLineNumber(),
            });
          }
        }
      }
    }

    // --- GraphQL hook calls: useQuery(...), useMutation(...) ---
    if (Node.isIdentifier(expr) && GRAPHQL_IDENTIFIERS.has(expr.getText())) {
      calls.push({
        url: "<graphql>",
        method: expr.getText().toUpperCase(),
        line: call.getStartLineNumber(),
      });
    }
  }
  return calls;
}

function extractStringValue(node: Node | undefined): string | undefined {
  if (!node) return undefined;
  if (Node.isStringLiteral(node)) {
    return node.getLiteralValue();
  }
  if (Node.isNoSubstitutionTemplateLiteral(node)) {
    return node.getLiteralValue();
  }
  if (Node.isTemplateExpression(node)) {
    // Return the head text with a placeholder
    const head = node.getHead().getLiteralValue();
    return head ? `${head}<dynamic>` : "<dynamic>";
  }
  return undefined;
}

function extractMethodFromOptions(node: Node | undefined): string | undefined {
  if (!node || !Node.isObjectLiteralExpression(node)) return undefined;
  for (const prop of node.getProperties()) {
    if (
      Node.isPropertyAssignment(prop) &&
      prop.getName() === "method"
    ) {
      const init = prop.getInitializer();
      if (init) {
        const val = extractStringValue(init);
        if (val) return val.toUpperCase();
      }
    }
  }
  return undefined;
}

/** Infer HTTP method from a typed API client method name. */
function inferHttpMethod(methodName: string): string {
  const lower = methodName.toLowerCase();
  if (lower.startsWith("get") || lower.startsWith("fetch") || lower.startsWith("list") || lower.startsWith("find")) return "GET";
  if (lower.startsWith("create") || lower.startsWith("add") || lower.startsWith("post")) return "POST";
  if (lower.startsWith("update") || lower.startsWith("edit") || lower.startsWith("put")) return "PUT";
  if (lower.startsWith("patch")) return "PATCH";
  if (lower.startsWith("delete") || lower.startsWith("remove")) return "DELETE";
  return "UNKNOWN";
}

// ---------------------------------------------------------------------------
// Hook extraction
// ---------------------------------------------------------------------------

function extractHooks(body: Node): string[] {
  const hooks: string[] = [];
  const seen = new Set<string>();
  const callExpressions = body.getDescendantsOfKind(SyntaxKind.CallExpression);
  for (const call of callExpressions) {
    const expr = call.getExpression();
    let name: string | undefined;
    if (Node.isIdentifier(expr)) {
      name = expr.getText();
    } else if (Node.isPropertyAccessExpression(expr)) {
      // React.useState, React.useEffect, etc.
      name = expr.getName();
    }
    if (name && isHookName(name) && !seen.has(name)) {
      seen.add(name);
      hooks.push(name);
    }
  }
  return hooks;
}

// ---------------------------------------------------------------------------
// JSX children extraction
// ---------------------------------------------------------------------------

function extractJsxChildren(body: Node): string[] {
  const children = new Set<string>();

  const openingElements = body.getDescendantsOfKind(SyntaxKind.JsxOpeningElement);
  for (const elem of openingElements) {
    const tagName = elem.getTagNameNode().getText();
    if (isPascalCase(tagName.split(".")[0])) {
      children.add(tagName);
    }
  }

  const selfClosing = body.getDescendantsOfKind(SyntaxKind.JsxSelfClosingElement);
  for (const elem of selfClosing) {
    const tagName = elem.getTagNameNode().getText();
    if (isPascalCase(tagName.split(".")[0])) {
      children.add(tagName);
    }
  }

  return Array.from(children);
}

// ---------------------------------------------------------------------------
// Props extraction from function parameters
// ---------------------------------------------------------------------------

function extractProps(params: ParameterDeclaration[]): string[] {
  if (params.length === 0) return [];
  const firstParam = params[0];

  // Destructured props: ({ foo, bar }) => ...
  const bindingPattern = firstParam.getNameNode();
  if (Node.isObjectBindingPattern(bindingPattern)) {
    return bindingPattern.getElements().map((e) => e.getName());
  }

  // Typed props: (props: MyProps) => ...
  // Try to get the type's properties
  const typeNode = firstParam.getTypeNode();
  if (typeNode) {
    const type = firstParam.getType();
    const properties = type.getProperties();
    if (properties.length > 0 && properties.length <= 50) {
      return properties.map((p) => p.getName());
    }
  }

  return [];
}

// ---------------------------------------------------------------------------
// Core analysis
// ---------------------------------------------------------------------------

function analyzeSourceFile(
  sourceFile: SourceFile,
  rootDir: string
): {
  module: ModuleInfo;
  functions: FunctionInfo[];
  components: ComponentInfo[];
  customHooks: CustomHookInfo[];
  apiCallSites: ApiCallSiteInfo[];
  importEdges: ImportGraphEdge[];
} {
  const filePath = sourceFile.getFilePath();
  const relFile = fileKey(filePath, rootDir);

  // --- Module info ---
  const imports: ImportInfo[] = [];
  const importEdges: ImportGraphEdge[] = [];

  for (const decl of sourceFile.getImportDeclarations()) {
    const source = decl.getModuleSpecifierValue();
    const internal = isInternalImport(source);
    const specifiers: string[] = [];

    const defaultImport = decl.getDefaultImport();
    if (defaultImport) specifiers.push(defaultImport.getText());

    const namespaceImport = decl.getNamespaceImport();
    if (namespaceImport) specifiers.push(`* as ${namespaceImport.getText()}`);

    for (const named of decl.getNamedImports()) {
      specifiers.push(named.getName());
    }

    imports.push({ source, specifiers, is_internal: internal });

    if (internal) {
      const resolvedTo = resolveImportPath(filePath, source);
      const fromKey = filePath.replace(/\.(tsx?|jsx?|mjs|cjs)$/, "");
      importEdges.push({
        from: fileKey(fromKey, rootDir),
        to: fileKey(resolvedTo, rootDir),
      });
    }
  }

  // --- Exports ---
  const exports: ExportInfo[] = [];
  for (const exp of sourceFile.getExportedDeclarations()) {
    const [name, declarations] = exp;
    for (const decl of declarations) {
      let kind = "variable";
      if (Node.isFunctionDeclaration(decl)) kind = "function";
      else if (Node.isClassDeclaration(decl)) kind = "class";
      else if (Node.isTypeAliasDeclaration(decl)) kind = "type";
      else if (Node.isInterfaceDeclaration(decl)) kind = "interface";
      else if (Node.isEnumDeclaration(decl)) kind = "variable";
      exports.push({ name: name === "default" ? "default" : name, kind });
    }
  }

  const moduleInfo: ModuleInfo = {
    name: relFile.replace(/\.(tsx?|jsx?|mjs|cjs)$/, ""),
    file: relFile,
    imports,
    exports,
  };

  // --- Functions, components, hooks ---
  const functions: FunctionInfo[] = [];
  const components: ComponentInfo[] = [];
  const customHooks: CustomHookInfo[] = [];
  const apiCallSites: ApiCallSiteInfo[] = [];

  // Process function declarations
  for (const func of sourceFile.getFunctions()) {
    const name = func.getName();
    if (!name) continue;
    processFunctionLike(name, func, func.getParameters(), func.isAsync(), relFile, rootDir, functions, components, customHooks, apiCallSites);
  }

  // Process variable declarations (arrow functions, function expressions)
  for (const varStatement of sourceFile.getVariableStatements()) {
    for (const decl of varStatement.getDeclarations()) {
      const name = decl.getName();
      const initializer = decl.getInitializer();
      if (!initializer) continue;

      let funcNode: ArrowFunction | FunctionExpression | undefined;
      if (Node.isArrowFunction(initializer)) {
        funcNode = initializer;
      } else if (Node.isFunctionExpression(initializer)) {
        funcNode = initializer;
      }
      // Handle React.forwardRef, React.memo wrapping
      if (!funcNode && Node.isCallExpression(initializer)) {
        const innerArg = initializer.getArguments()[0];
        if (innerArg && Node.isArrowFunction(innerArg)) {
          funcNode = innerArg;
        } else if (innerArg && Node.isFunctionExpression(innerArg)) {
          funcNode = innerArg;
        }
      }

      if (funcNode) {
        processFunctionLike(
          name,
          funcNode,
          funcNode.getParameters(),
          funcNode.isAsync(),
          relFile,
          rootDir,
          functions,
          components,
          customHooks,
          apiCallSites
        );
      }
    }
  }

  // Process class declarations (class components)
  for (const cls of sourceFile.getClasses()) {
    const name = cls.getName();
    if (!name) continue;

    // Detect class component by checking if it extends React.Component / React.PureComponent
    const extendsExpr = cls.getExtends();
    if (extendsExpr) {
      const extendsText = extendsExpr.getText();
      if (
        extendsText.includes("Component") ||
        extendsText.includes("PureComponent")
      ) {
        const hooks: string[] = []; // class components don't use hooks
        const children: string[] = [];
        const props: string[] = [];
        const componentApiCalls: ApiCallInfo[] = [];

        // Look for render method
        const renderMethod = cls.getMethod("render");
        if (renderMethod) {
          const body = renderMethod.getBody();
          if (body) {
            children.push(...extractJsxChildren(body));
            const rawCalls = extractApiCalls(body);
            for (const rc of rawCalls) {
              componentApiCalls.push({ url: rc.url, method: rc.method });
              apiCallSites.push({
                component_or_function: name,
                url: rc.url,
                method: rc.method,
                file: relFile,
                line: rc.line,
              });
            }
          }
        }

        // Try to extract props from type parameter
        const typeArgs = extendsExpr.getTypeArguments();
        if (typeArgs.length > 0) {
          const propsType = typeArgs[0].getType();
          const propsProperties = propsType.getProperties();
          if (propsProperties.length > 0 && propsProperties.length <= 50) {
            props.push(...propsProperties.map((p) => p.getName()));
          }
        }

        // Also collect API calls from all methods
        for (const method of cls.getMethods()) {
          if (method.getName() === "render") continue;
          const body = method.getBody();
          if (body) {
            const rawCalls = extractApiCalls(body);
            for (const rc of rawCalls) {
              componentApiCalls.push({ url: rc.url, method: rc.method });
              apiCallSites.push({
                component_or_function: name,
                url: rc.url,
                method: rc.method,
                file: relFile,
                line: rc.line,
              });
            }
          }
        }

        components.push({
          name,
          file: relFile,
          line_start: cls.getStartLineNumber(),
          line_end: cls.getEndLineNumber(),
          hooks,
          children,
          props,
          is_exported: isNodeExported(cls),
          api_calls: deduplicateApiCalls(componentApiCalls),
        });
        continue;
      }
    }

    // Non-component class: extract methods as functions
    for (const method of cls.getMethods()) {
      const methodName = method.getName();
      functions.push({
        name: methodName,
        qualified_name: `${name}.${methodName}`,
        file: relFile,
        line_start: method.getStartLineNumber(),
        line_end: method.getEndLineNumber(),
        is_async: method.isAsync(),
        is_exported: isNodeExported(cls),
        parameters: method.getParameters().map(extractParameter),
      });
    }
  }

  return {
    module: moduleInfo,
    functions,
    components,
    customHooks,
    apiCallSites,
    importEdges,
  };
}

function processFunctionLike(
  name: string,
  node: FunctionDeclaration | ArrowFunction | FunctionExpression,
  params: ParameterDeclaration[],
  isAsync: boolean,
  relFile: string,
  rootDir: string,
  functions: FunctionInfo[],
  components: ComponentInfo[],
  customHooks: CustomHookInfo[],
  apiCallSites: ApiCallSiteInfo[]
): void {
  const body = Node.isFunctionDeclaration(node) ? node.getBody() : node.getBody();
  const exported = isNodeExported(node);
  const lineStart = node.getStartLineNumber();
  const lineEnd = node.getEndLineNumber();

  // Custom hook detection (takes priority over component detection)
  if (isHookName(name)) {
    const hooksUsed: string[] = body ? extractHooks(body) : [];
    customHooks.push({
      name,
      file: relFile,
      hooks_used: hooksUsed,
    });

    // Also collect API calls inside custom hooks
    if (body) {
      const rawCalls = extractApiCalls(body);
      for (const rc of rawCalls) {
        apiCallSites.push({
          component_or_function: name,
          url: rc.url,
          method: rc.method,
          file: relFile,
          line: rc.line,
        });
      }
    }

    // Custom hooks are also recorded as functions
    functions.push({
      name,
      qualified_name: name,
      file: relFile,
      line_start: lineStart,
      line_end: lineEnd,
      is_async: isAsync,
      is_exported: exported,
      parameters: params.map(extractParameter),
    });
    return;
  }

  // React component detection: PascalCase name + returns JSX (or has hooks)
  if (isPascalCase(name) && body) {
    const hooks = extractHooks(body);
    const hasJsx =
      body.getDescendantsOfKind(SyntaxKind.JsxElement).length > 0 ||
      body.getDescendantsOfKind(SyntaxKind.JsxSelfClosingElement).length > 0 ||
      body.getDescendantsOfKind(SyntaxKind.JsxFragment).length > 0;

    if (hasJsx || hooks.length > 0) {
      const children = extractJsxChildren(body);
      const props = extractProps(params);
      const rawCalls = extractApiCalls(body);
      const componentApiCalls: ApiCallInfo[] = rawCalls.map((rc) => ({
        url: rc.url,
        method: rc.method,
      }));
      for (const rc of rawCalls) {
        apiCallSites.push({
          component_or_function: name,
          url: rc.url,
          method: rc.method,
          file: relFile,
          line: rc.line,
        });
      }

      components.push({
        name,
        file: relFile,
        line_start: lineStart,
        line_end: lineEnd,
        hooks,
        children,
        props,
        is_exported: exported,
        api_calls: deduplicateApiCalls(componentApiCalls),
      });
      return;
    }
  }

  // Regular function
  const rawCalls = body ? extractApiCalls(body) : [];
  for (const rc of rawCalls) {
    apiCallSites.push({
      component_or_function: name,
      url: rc.url,
      method: rc.method,
      file: relFile,
      line: rc.line,
    });
  }

  functions.push({
    name,
    qualified_name: name,
    file: relFile,
    line_start: lineStart,
    line_end: lineEnd,
    is_async: isAsync,
    is_exported: exported,
    parameters: params.map(extractParameter),
  });
}

function deduplicateApiCalls(calls: ApiCallInfo[]): ApiCallInfo[] {
  const seen = new Set<string>();
  const result: ApiCallInfo[] = [];
  for (const call of calls) {
    const key = `${call.method}:${call.url}`;
    if (!seen.has(key)) {
      seen.add(key);
      result.push(call);
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Summary generation
// ---------------------------------------------------------------------------

function generateSummary(
  modules: ModuleInfo[],
  functions: FunctionInfo[],
  components: ComponentInfo[],
  customHooks: CustomHookInfo[]
): SummaryInfo {
  // Top components: most referenced as children by other components
  const childRefCount = new Map<string, number>();
  for (const comp of components) {
    for (const child of comp.children) {
      childRefCount.set(child, (childRefCount.get(child) || 0) + 1);
    }
  }
  const topComponents = Array.from(childRefCount.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name]) => name);

  // Complex components: highest number of hooks + children + api_calls
  const complexComponents = [...components]
    .map((c) => ({
      name: c.name,
      complexity: c.hooks.length + c.children.length + c.api_calls.length,
    }))
    .sort((a, b) => b.complexity - a.complexity)
    .slice(0, 10)
    .map((c) => c.name);

  return {
    total_modules: modules.length,
    total_components: components.length,
    total_functions: functions.length,
    total_custom_hooks: customHooks.length,
    top_components: topComponents,
    complex_components: complexComponents,
  };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main(): void {
  const args = parseArgs();

  console.log(`Analyzing TypeScript project at: ${args.directory}`);

  // Create ts-morph project
  const projectOptions: ConstructorParameters<typeof Project>[0] = {
    skipAddingFilesFromTsConfig: true,
    skipFileDependencyResolution: true,
    compilerOptions: {
      allowJs: true,
      jsx: ts.JsxEmit.ReactJSX,
      strict: false,
      noEmit: true,
      esModuleInterop: true,
      moduleResolution: ts.ModuleResolutionKind.NodeNext,
      module: ts.ModuleKind.NodeNext,
      target: ts.ScriptTarget.ES2022,
    },
  };

  if (args.tsconfig && fs.existsSync(args.tsconfig)) {
    projectOptions.tsConfigFilePath = args.tsconfig;
    projectOptions.skipAddingFilesFromTsConfig = false;
    // When using tsconfig, remove manual compiler options to let tsconfig drive
    delete projectOptions.compilerOptions;
    console.log(`Using tsconfig: ${args.tsconfig}`);
  }

  const project = new Project(projectOptions);

  // If no tsconfig, manually add source files
  if (!args.tsconfig || !fs.existsSync(args.tsconfig)) {
    project.addSourceFilesAtPaths([
      path.join(args.directory, "**/*.ts"),
      path.join(args.directory, "**/*.tsx"),
      path.join(args.directory, "**/*.js"),
      path.join(args.directory, "**/*.jsx"),
    ]);
  }

  const sourceFiles = project.getSourceFiles().filter(
    (sf) => !shouldSkipFile(sf.getFilePath())
  );

  console.log(`Found ${sourceFiles.length} source files to analyze.`);

  const allModules: ModuleInfo[] = [];
  const allFunctions: FunctionInfo[] = [];
  const allComponents: ComponentInfo[] = [];
  const allCustomHooks: CustomHookInfo[] = [];
  const allApiCallSites: ApiCallSiteInfo[] = [];
  const allImportEdges: ImportGraphEdge[] = [];

  for (const sourceFile of sourceFiles) {
    try {
      const result = analyzeSourceFile(sourceFile, args.directory);
      allModules.push(result.module);
      allFunctions.push(...result.functions);
      allComponents.push(...result.components);
      allCustomHooks.push(...result.customHooks);
      allApiCallSites.push(...result.apiCallSites);
      allImportEdges.push(...result.importEdges);
    } catch (err) {
      const filePath = sourceFile.getFilePath();
      console.warn(`Warning: failed to analyze ${filePath}: ${err}`);
    }
  }

  // Deduplicate import graph edges
  const edgeSet = new Set<string>();
  const uniqueEdges: ImportGraphEdge[] = [];
  for (const edge of allImportEdges) {
    const key = `${edge.from}->${edge.to}`;
    if (!edgeSet.has(key)) {
      edgeSet.add(key);
      uniqueEdges.push(edge);
    }
  }

  const summary = generateSummary(
    allModules,
    allFunctions,
    allComponents,
    allCustomHooks
  );

  const result: AnalysisResult = {
    modules: allModules,
    functions: allFunctions,
    components: allComponents,
    custom_hooks: allCustomHooks,
    import_graph: uniqueEdges,
    api_call_sites: allApiCallSites,
    summary,
  };

  // Write output
  const outputDir = path.dirname(args.output);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  fs.writeFileSync(args.output, JSON.stringify(result, null, 2), "utf-8");
  console.log(`\nAnalysis complete. Results written to: ${args.output}`);
  console.log(`  Modules:      ${summary.total_modules}`);
  console.log(`  Components:   ${summary.total_components}`);
  console.log(`  Functions:    ${summary.total_functions}`);
  console.log(`  Custom Hooks: ${summary.total_custom_hooks}`);
  console.log(`  API Call Sites: ${allApiCallSites.length}`);
  console.log(`  Import Graph Edges: ${uniqueEdges.length}`);

  if (summary.top_components.length > 0) {
    console.log(`\n  Top components (most referenced): ${summary.top_components.join(", ")}`);
  }
  if (summary.complex_components.length > 0) {
    console.log(`  Complex components: ${summary.complex_components.join(", ")}`);
  }
}

main();
