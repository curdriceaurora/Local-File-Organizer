#!/usr/bin/env python3
"""
GitHub Webhook Receiver for PR Monitoring

Listens for GitHub webhook events and triggers monitoring actions.
Handles: PR comments, CI status changes, approvals, ready-to-merge conditions.

Setup:
  1. Generate webhook secret: python3 -c "import secrets; print(secrets.token_hex(32))"
  2. Create GitHub webhook in repo settings
     - Payload URL: http://localhost:9000/webhook
     - Content type: application/json
     - Events: Pull requests, Pull request reviews, Workflow runs, Issue comments
     - Secret: Use secret from step 1
  3. Run this script: python3 .claude/scripts/webhook-receiver.py
  4. For remote access, use ngrok: ngrok http 9000
"""

import json
import hmac
import hashlib
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration
WEBHOOK_SECRET = (Path.home() / ".claude" / "webhook-secret").read_text().strip() if (Path.home() / ".claude" / "webhook-secret").exists() else ""
WEBHOOK_PORT = 9000
LOG_FILE = Path.cwd() / ".claude" / "logs" / "webhook.log"

# Setup logging
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def verify_signature(payload_bytes, signature):
    """Verify GitHub webhook signature."""
    if not WEBHOOK_SECRET:
        logger.warning("No webhook secret configured - skipping signature verification")
        return True

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def handle_pull_request_event(payload):
    """Handle PR opened, reopened, synchronize events."""
    action = payload.get('action')
    pr = payload.get('pull_request', {})
    pr_number = pr.get('number')

    if not pr_number:
        return

    if action in ['opened', 'reopened', 'synchronize']:
        logger.info(f"🔔 PR #{pr_number} {action}")
        print(f"\n{'='*60}")
        print(f"PR #{pr_number} {action.upper()}")
        print(f"Title: {pr.get('title')}")
        print(f"URL: {pr.get('html_url')}")
        print(f"\nAction: /pm:issue-start {pr_number} (if not already tracking)")
        print(f"{'='*60}\n")


def handle_pull_request_review_event(payload):
    """Handle review submitted events."""
    action = payload.get('action')
    review = payload.get('review', {})
    pr = payload.get('pull_request', {})
    pr_number = pr.get('number')

    if action == 'submitted' and pr_number:
        state = review.get('state', 'commented')
        author = review.get('user', {}).get('login')

        if state == 'approved':
            logger.info(f"✅ PR #{pr_number} approved by @{author}")
            print(f"\n{'='*60}")
            print(f"✅ PR #{pr_number} APPROVED")
            print(f"Reviewer: @{author}")
            print(f"\nAction: Check merge conditions (CI passing? All comments resolved?)")
            print(f"{'='*60}\n")
        elif state == 'changes_requested':
            logger.info(f"🔴 PR #{pr_number} changes requested by @{author}")
            print(f"\n{'='*60}")
            print(f"🔴 CHANGES REQUESTED on PR #{pr_number}")
            print(f"Reviewer: @{author}")
            print(f"Comment: {review.get('body', '(no comment)')}")
            print(f"\nAction: /pm:issue-start {pr_number} to address findings")
            print(f"{'='*60}\n")


def handle_issue_comment_event(payload):
    """Handle comment on PR (from reviewers or bots like CodeRabbit)."""
    action = payload.get('action')
    if action != 'created':
        return

    issue = payload.get('issue', {})
    comment = payload.get('comment', {})
    author = comment.get('user', {}).get('login')
    issue_number = issue.get('number')

    if issue.get('pull_request') and issue_number:
        logger.info(f"💬 PR #{issue_number} comment from @{author}")

        # Check if this is from a code review bot (CodeRabbit, Copilot, etc.)
        if author in ['CodeRabbit', 'Copilot', 'gh-code-review']:
            print(f"\n{'='*60}")
            print(f"🤖 CODE REVIEW from @{author} on PR #{issue_number}")
            print(f"\nAction: /pm:issue-start {issue_number} to address findings")
            print(f"{'='*60}\n")
        else:
            print(f"\n{'='*60}")
            print(f"💬 Comment on PR #{issue_number} from @{author}")
            print(f"{'='*60}\n")


def handle_workflow_run_event(payload):
    """Handle CI workflow completion."""
    action = payload.get('action')
    if action != 'completed':
        return

    workflow_run = payload.get('workflow_run', {})
    pr_list = workflow_run.get('pull_requests', [])

    if not pr_list:
        return

    pr = pr_list[0]
    pr_number = pr.get('number')
    conclusion = workflow_run.get('conclusion')

    if conclusion == 'success':
        logger.info(f"✅ CI PASSED for PR #{pr_number}")
        print(f"\n{'='*60}")
        print(f"✅ CI PASSED on PR #{pr_number}")
        print(f"\nAction: Check if ready to merge:")
        print(f"  - CI passing? ✅")
        print(f"  - All comments resolved?")
        print(f"  - 1 approval received?")
        print(f"\nIf YES to all: Enable auto-merge on PR")
        print(f"{'='*60}\n")
    elif conclusion == 'failure':
        logger.info(f"❌ CI FAILED for PR #{pr_number}")
        print(f"\n{'='*60}")
        print(f"❌ CI FAILED on PR #{pr_number}")
        print(f"\nAction: /pm:issue-start {pr_number} to fix CI failure")
        print(f"{'='*60}\n")


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for GitHub webhooks."""

    def do_POST(self):
        """Handle POST requests (webhook deliveries)."""
        if self.path != '/webhook':
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get('Content-Length', 0))
        payload_bytes = self.rfile.read(content_length)

        # Verify signature
        signature = self.headers.get('X-Hub-Signature-256', '')
        if not verify_signature(payload_bytes, signature):
            logger.warning("Invalid webhook signature")
            self.send_response(401)
            self.end_headers()
            return

        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            self.send_response(400)
            self.end_headers()
            return

        # Route to appropriate handler
        event_type = self.headers.get('X-GitHub-Event', '')

        if event_type == 'pull_request':
            handle_pull_request_event(payload)
        elif event_type == 'pull_request_review':
            handle_pull_request_review_event(payload)
        elif event_type == 'issue_comment':
            handle_issue_comment_event(payload)
        elif event_type == 'workflow_run':
            handle_workflow_run_event(payload)

        # Log the event
        logger.info(f"Webhook: {event_type} - {payload.get('action', 'N/A')}")

        # Always return 200 OK
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "received"}')

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass


def main():
    """Start the webhook receiver."""
    if not WEBHOOK_SECRET:
        print("⚠️  No webhook secret found!")
        print("\nSetup:")
        print("  1. Generate secret: python3 -c \"import secrets; print(secrets.token_hex(32))\"")
        print(f"  2. Save to: ~/.claude/webhook-secret")
        print("  3. Use secret when creating GitHub webhook")
        print("\nWithout this, webhook signature verification will be skipped.")

    server = HTTPServer(('localhost', WEBHOOK_PORT), WebhookHandler)
    logger.info(f"Webhook receiver listening on port {WEBHOOK_PORT}")
    print(f"\n{'='*60}")
    print(f"🚀 Webhook Receiver Started")
    print(f"Listening on: http://localhost:{WEBHOOK_PORT}/webhook")
    print(f"Logs: {LOG_FILE}")
    print(f"\nTo expose to GitHub (if on different network):")
    print(f"  ngrok http {WEBHOOK_PORT}")
    print(f"\nThen add webhook to GitHub repo settings:")
    print(f"  - Payload URL: http://localhost:{WEBHOOK_PORT}/webhook (or ngrok URL)")
    print(f"  - Content type: application/json")
    print(f"  - Events: Pull requests, Reviews, Comments, Workflow runs")
    print(f"  - Secret: (value from ~/.claude/webhook-secret)")
    print(f"{'='*60}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Webhook receiver stopped")
        print("\nWebhook receiver stopped")


if __name__ == '__main__':
    main()
