#!/usr/bin/env node
// Bridge de análisis estático JS/TS.
//
// Reutiliza @babel/parser (dependencia MIT ya presente en la instalación de REA).
// Recibe: --root <dir> [--parser <ruta>] [--max-file-bytes N] [--max-files N]
// Emite: un único objeto JSON en stdout con los hechos por archivo.
//
// No ejecuta el código analizado: solo lo parsea.

import { readdir, readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import path from "node:path";

const IGNORED_DIRS = new Set([
  "node_modules", ".git", ".hg", ".svn", "__pycache__", ".venv", "venv",
  "dist", "build", ".next", ".nuxt", "target", "coverage", ".cache",
  ".mypy_cache", ".pytest_cache", "vendor",
]);

const EXT_LANGUAGE = {
  ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
  ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
};

function parseArgs(argv) {
  const args = { root: null, parser: null, maxFileBytes: 2 * 1024 * 1024, maxFiles: 20000 };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--root") args.root = argv[++i];
    else if (token === "--parser") args.parser = argv[++i];
    else if (token === "--max-file-bytes") args.maxFileBytes = Number(argv[++i]);
    else if (token === "--max-files") args.maxFiles = Number(argv[++i]);
  }
  return args;
}

async function loadParser(parserPath) {
  let mod;
  if (parserPath) {
    mod = await import(pathToFileURL(parserPath).href);
  } else {
    mod = await import("@babel/parser");
  }
  const parse = mod.parse || (mod.default && mod.default.parse);
  if (typeof parse !== "function") {
    throw new Error("No se pudo resolver parse() de @babel/parser");
  }
  return parse;
}

function calleeName(node) {
  if (!node) return null;
  if (node.type === "Identifier") return node.name;
  if (node.type === "MemberExpression") {
    const object = calleeName(node.object);
    const property = node.computed
      ? node.property && node.property.type === "StringLiteral"
        ? node.property.value
        : null
      : calleeName(node.property);
    if (object && property) return `${object}.${property}`;
    return null;
  }
  return null;
}

function pluginsFor(language, filePath) {
  const plugins = [];
  if (language === "typescript") plugins.push("typescript");
  if (filePath.endsWith(".tsx") || filePath.endsWith(".jsx")) plugins.push("jsx");
  plugins.push("decorators-legacy");
  return plugins;
}

function walk(node, visit) {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) {
    for (const item of node) walk(item, visit);
    return;
  }
  if (typeof node.type === "string") visit(node);
  for (const key of Object.keys(node)) {
    if (key === "loc" || key === "start" || key === "end" || key === "range") continue;
    const value = node[key];
    if (value && typeof value === "object") walk(value, visit);
  }
}

function analyzeSource(parse, source, language, filePath) {
  const facts = {
    path: filePath,
    language,
    parse_ok: true,
    error: null,
    imports: [],
    requires: [],
    functions: [],
    classes: [],
    env_vars: [],
    calls: [],
    has_default_export: false,
    parse_error_line: null,
  };
  let ast;
  try {
    ast = parse(source, {
      sourceType: "unambiguous",
      errorRecovery: false,
      plugins: pluginsFor(language, filePath),
    });
  } catch (error) {
    facts.parse_ok = false;
    facts.error = String(error && error.message ? error.message : error);
    facts.parse_error_line = error && error.loc ? error.loc.line : null;
    return facts;
  }

  walk(ast, (node) => {
    switch (node.type) {
      case "ImportDeclaration":
        if (node.source && typeof node.source.value === "string") {
          facts.imports.push({
            source: node.source.value,
            line: node.loc ? node.loc.start.line : 0,
            names: (node.specifiers || []).map((s) => s.local && s.local.name).filter(Boolean),
            kind: "import",
          });
        }
        break;
      case "ExportDefaultDeclaration":
        facts.has_default_export = true;
        break;
      case "FunctionDeclaration":
        if (node.id && node.id.name) {
          facts.functions.push({ name: node.id.name, line: node.loc ? node.loc.start.line : 0, is_async: !!node.async });
        }
        break;
      case "ClassDeclaration":
        if (node.id && node.id.name) {
          facts.classes.push({ name: node.id.name, line: node.loc ? node.loc.start.line : 0 });
        }
        break;
      case "VariableDeclarator":
        if (
          node.id &&
          node.id.type === "Identifier" &&
          node.init &&
          (node.init.type === "ArrowFunctionExpression" || node.init.type === "FunctionExpression")
        ) {
          facts.functions.push({
            name: node.id.name,
            line: node.loc ? node.loc.start.line : 0,
            is_async: !!node.init.async,
          });
        }
        break;
      case "CallExpression": {
        const name = calleeName(node.callee);
        const line = node.loc ? node.loc.start.line : 0;
        if (name) facts.calls.push({ callee: name, line, is_new: false });
        if (name === "require" && node.arguments && node.arguments[0] && node.arguments[0].type === "StringLiteral") {
          facts.requires.push({ source: node.arguments[0].value, line, kind: "require" });
        }
        if (name && (name === "process.env" || name.startsWith("process.env."))) {
          // cubierto por MemberExpression abajo
        }
        break;
      }
      case "NewExpression": {
        const name = calleeName(node.callee);
        if (name) facts.calls.push({ callee: name, line: node.loc ? node.loc.start.line : 0, is_new: true });
        break;
      }
      case "MemberExpression": {
        const line = node.loc ? node.loc.start.line : 0;
        const obj = calleeName(node.object);
        if (obj === "process.env") {
          if (node.computed && node.property && node.property.type === "StringLiteral") {
            facts.env_vars.push({ name: node.property.value, line });
          } else if (!node.computed && node.property && node.property.type === "Identifier") {
            facts.env_vars.push({ name: node.property.name, line });
          }
        }
        break;
      }
      default:
        break;
    }
  });

  return facts;
}

async function collectFiles(root, maxFiles) {
  const results = [];
  const stack = [root];
  while (stack.length > 0) {
    if (results.length >= maxFiles) break;
    const current = stack.pop();
    let entries;
    try {
      entries = await readdir(current, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (results.length >= maxFiles) break;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (IGNORED_DIRS.has(entry.name) || entry.name.startsWith(".")) continue;
        stack.push(full);
      } else if (entry.isFile()) {
        if (EXT_LANGUAGE[path.extname(entry.name).toLowerCase()]) {
          results.push(full);
        }
      }
    }
  }
  return results;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.root) {
    process.stdout.write(JSON.stringify({ version: 1, error: "Falta --root" }));
    process.exit(2);
  }
  let parse;
  try {
    parse = await loadParser(args.parser);
  } catch (error) {
    process.stdout.write(
      JSON.stringify({ version: 1, parser_resolved: false, error: String(error.message || error), files: [] }),
    );
    process.exit(0);
  }

  const files = await collectFiles(args.root, args.maxFiles);
  const output = { version: 1, parser_resolved: true, root: args.root, files: [], skipped: [] };
  for (const filePath of files) {
    let source;
    try {
      const stat = await readFile(filePath);
      if (stat.byteLength > args.maxFileBytes) {
        output.skipped.push({ path: path.relative(args.root, filePath), reason: "oversized" });
        continue;
      }
      source = stat.toString("utf8");
    } catch (error) {
      output.skipped.push({ path: path.relative(args.root, filePath), reason: String(error.message) });
      continue;
    }
    const language = EXT_LANGUAGE[path.extname(filePath).toLowerCase()];
    const relative = path.relative(args.root, filePath).split(path.sep).join("/");
    output.files.push(analyzeSource(parse, source, language, relative));
  }
  process.stdout.write(JSON.stringify(output));
}

main().catch((error) => {
  process.stdout.write(JSON.stringify({ version: 1, fatal: String(error && error.message ? error.message : error), files: [] }));
  process.exit(1);
});
