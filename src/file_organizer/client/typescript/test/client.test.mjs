import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { afterEach, test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  ClientError,
  FileOrganizerClient,
  ValidationError,
} from "../client.ts";
import {
  inventoryPath,
  readPublicClientMethods,
} from "../scripts/method-inventory.mjs";

const testDirectory = dirname(fileURLToPath(import.meta.url));
const packageDirectory = resolve(testDirectory, "..");
const repositoryRoot = resolve(packageDirectory, "../../../..");
const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function captureFetch(responsePayload, status = 200) {
  const calls = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ input: String(input), init });
    return jsonResponse(responsePayload, status);
  };
  return calls;
}

test("public endpoint inventory matches source, endpoint spec, and generated artifact", () => {
  const declared = readPublicClientMethods();
  const inventory = JSON.parse(readFileSync(inventoryPath, "utf8"));
  const python = process.env.PYTHON ?? "python3";
  const expected = JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        "import json; from file_organizer.client.endpoint_spec import PUBLIC_ENDPOINTS; " +
          "print(json.dumps(sorted({endpoint.typescript_method for endpoint in PUBLIC_ENDPOINTS})))",
      ],
      {
        cwd: repositoryRoot,
        encoding: "utf8",
        env: {
          ...process.env,
          PYTHONPATH: resolve(repositoryRoot, "src"),
        },
      }
    )
  );

  assert.equal(inventory.schema_version, 1);
  assert.deepEqual(inventory.methods, declared);
  assert.deepEqual(inventory.methods, expected);
});

test("scan sends canonical traversal options and returns ordered files", async () => {
  const calls = captureFetch({
    input_dir: "/input",
    total_files: 2,
    files: ["/input/a.txt", "/input/nested/b.md"],
    counts: { text: 2 },
  });
  const client = new FileOrganizerClient({ baseUrl: "https://example.test" });

  const result = await client.scan("/input", { recursive: false, includeHidden: true });

  assert.deepEqual(result.files, ["/input/a.txt", "/input/nested/b.md"]);
  assert.equal(calls[0].input, "https://example.test/api/v1/organize/scan");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    input_dir: "/input",
    recursive: false,
    include_hidden: true,
  });
});

test("organization methods preserve canonical options, plans, and idempotency", async () => {
  const plan = {
    plan_id: "plan-1",
    schema_version: 3,
    input_path: "/input",
    output_path: "/output",
    created_at: "2026-01-01T00:00:00Z",
    skip_existing: false,
    use_hardlinks: false,
    total_files: 0,
    processed_files: 0,
    skipped_files: 0,
    failed_files: 0,
    deduplicated_files: 0,
    options: null,
    operations: [],
    errors: [],
    metadata: {},
  };
  const calls = captureFetch({ status: "queued", job_id: "job-1", result: null, error: null });
  const client = new FileOrganizerClient({ baseUrl: "https://example.test/" });

  await client.organize("/input", "/output", {
    options: {
      recursive: false,
      include_hidden: true,
      skip_existing: false,
      transfer_mode: "copy",
      methodology: "para",
      transcribe_audio: true,
      parallel_workers: 3,
    },
    plan,
    runInBackground: true,
    idempotencyKey: "request-1",
  });

  assert.equal(calls[0].input, "https://example.test/api/v1/organize/execute");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    input_dir: "/input",
    output_dir: "/output",
    options: {
      recursive: false,
      include_hidden: true,
      skip_existing: false,
      transfer_mode: "copy",
      methodology: "para",
      transcribe_audio: true,
      parallel_workers: 3,
    },
    plan,
    dry_run: false,
    run_in_background: true,
    idempotency_key: "request-1",
  });
});

test("typed errors preserve stable code, retryability, and details", async () => {
  captureFetch(
    {
      error: "validation_error",
      message: "Invalid request payload.",
      retryable: true,
      details: [{ loc: ["body", "input_dir"], msg: "Field required" }],
    },
    422
  );
  const client = new FileOrganizerClient({ baseUrl: "https://example.test" });

  await assert.rejects(
    client.scan("/input"),
    (error) =>
      error instanceof ClientError &&
      error instanceof ValidationError &&
      error.errorCode === "validation_error" &&
      error.retryable === true &&
      Array.isArray(error.details)
  );
});
