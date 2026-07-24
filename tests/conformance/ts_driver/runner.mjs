import { FileOrganizerClient, ClientError } from "../../../src/file_organizer/client/typescript/client.ts";

async function main() {
  const [,, action, baseUrl, inputDir, outputDir, optionsJson, planJson] = process.argv;

  if (!action || !baseUrl || !inputDir) {
    console.error("Usage: runner.mjs <action> <baseUrl> <inputDir> [outputDir] [optionsJson] [planJson]");
    process.exit(2);
  }

  const client = new FileOrganizerClient({ baseUrl });
  const options = optionsJson ? JSON.parse(optionsJson) : undefined;
  const plan = planJson ? JSON.parse(planJson) : undefined;

  try {
    if (action === "scan") {
      const response = await client.scan(inputDir, {
        recursive: options?.recursive ?? true,
        includeHidden: options?.include_hidden ?? false,
      });
      console.log(JSON.stringify({ outcome: "ok", payload: response }));
    } else if (action === "preview") {
      const response = await client.previewOrganize(inputDir, outputDir, {
        options,
        skipExisting: options?.skip_existing,
        useHardlinks: options?.use_hardlinks,
      });
      console.log(JSON.stringify({ outcome: "ok", payload: response }));
    } else if (action === "execute") {
      const response = await client.organize(inputDir, outputDir, {
        options,
        plan,
        dryRun: false,
        runInBackground: false,
        skipExisting: options?.skip_existing,
        useHardlinks: options?.use_hardlinks,
      });
      if (!response || !response.result) {
        throw new Error(`TS SDK execution omitted its result: ${JSON.stringify(response)}`);
      }
      console.log(JSON.stringify({ outcome: "ok", payload: response.result }));
    } else {
      throw new Error(`Unknown action: ${action}`);
    }
  } catch (err) {
    if (err instanceof ClientError) {
      console.log(
        JSON.stringify({
          outcome: "error",
          error: {
            code: err.errorCode || err.name,
            error: err.errorCode || err.name,
            message: err.detail || err.message,
            retryable: err.retryable || false,
            details: err.details,
          },
        })
      );
    } else {
      console.log(
        JSON.stringify({
          outcome: "exception",
          message: err instanceof Error ? err.message : String(err),
        })
      );
    }
  }
}

main();
