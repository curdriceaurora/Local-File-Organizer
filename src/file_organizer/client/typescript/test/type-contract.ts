import { FileOrganizerClient } from "../client";

const client = new FileOrganizerClient();

void client.scan("/input", { recursive: false, includeHidden: true });
void client.previewOrganize("/input", "/output", {
  options: { transfer_mode: "copy", methodology: "para" },
});
void client.organize("/input", "/output", {
  runInBackground: true,
  idempotencyKey: "request-1",
});

// @ts-expect-error recursive must remain boolean.
void client.scan("/input", { recursive: "false" });
// @ts-expect-error move is intentionally outside the canonical transfer contract.
void client.previewOrganize("/input", "/output", { options: { transfer_mode: "move" } });
