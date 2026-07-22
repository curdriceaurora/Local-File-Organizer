import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import ts from "typescript";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
export const packageDirectory = resolve(scriptDirectory, "..");
export const inventoryPath = resolve(packageDirectory, "methods.generated.json");

export function readPublicClientMethods() {
  const sourcePath = resolve(packageDirectory, "client.ts");
  const source = readFileSync(sourcePath, "utf8");
  const tree = ts.createSourceFile(sourcePath, source, ts.ScriptTarget.Latest, true);
  const client = tree.statements.find(
    (statement) =>
      ts.isClassDeclaration(statement) && statement.name?.text === "FileOrganizerClient"
  );
  if (!client || !ts.isClassDeclaration(client)) {
    throw new Error("FileOrganizerClient class was not found");
  }

  return client.members
    .filter(ts.isMethodDeclaration)
    .filter(
      (member) =>
        !member.modifiers?.some(
          (modifier) =>
            modifier.kind === ts.SyntaxKind.PrivateKeyword ||
            modifier.kind === ts.SyntaxKind.ProtectedKeyword
        )
    )
    .map((member) => member.name)
    .filter(ts.isIdentifier)
    .map((name) => name.text)
    .filter((name) => name !== "setToken")
    .sort();
}

export function serializeInventory(methods = readPublicClientMethods()) {
  return `${JSON.stringify({ schema_version: 1, methods }, null, 2)}\n`;
}

function main() {
  const expected = serializeInventory();
  if (process.argv.includes("--check")) {
    const actual = readFileSync(inventoryPath, "utf8");
    if (actual !== expected) {
      throw new Error(
        "methods.generated.json is stale; run `npm run generate:methods` and commit the result"
      );
    }
    return;
  }
  writeFileSync(inventoryPath, expected, "utf8");
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  main();
}
