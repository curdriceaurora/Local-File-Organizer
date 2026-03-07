#!/bin/bash
# Setup GitHub Webhook for PR Monitoring

set -e

echo "🔐 GitHub Webhook Setup"
echo "======================="
echo ""

# Step 1: Generate webhook secret
echo "Step 1: Generating webhook secret..."
WEBHOOK_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
mkdir -p ~/.claude
echo "$WEBHOOK_SECRET" > ~/.claude/webhook-secret
chmod 600 ~/.claude/webhook-secret
echo "✅ Secret saved to ~/.claude/webhook-secret"
echo ""

# Step 2: Get repository info
echo "Step 2: Getting repository information..."
REPO_URL=$(git remote get-url origin)
REPO_NAME=$(echo "$REPO_URL" | sed 's|.*github.com/||' | sed 's|\.git$||')
REPO_OWNER=$(echo "$REPO_NAME" | cut -d/ -f1)
REPO_NAME=$(echo "$REPO_NAME" | cut -d/ -f2)

echo "Repository: $REPO_OWNER/$REPO_NAME"
echo ""

# Step 3: Instructions for GitHub configuration
echo "Step 3: Configure webhook in GitHub"
echo "====================================="
echo ""
echo "Manual Setup Required:"
echo "1. Go to: https://github.com/$REPO_OWNER/$REPO_NAME/settings/hooks"
echo "2. Click 'Add webhook'"
echo "3. Fill in:"
echo ""
echo "   Payload URL:"
echo "   - Local (if receiver running on your machine):"
echo "     http://localhost:9000/webhook"
echo ""
echo "   - Remote (to expose to internet via ngrok):"
echo "     1. Run: ngrok http 9000"
echo "     2. Use the ngrok URL: https://xxxx-xx-xxx-xxx.ngrok.io/webhook"
echo ""
echo "   Content type: application/json"
echo ""
echo "   Secret (copy-paste this entire value):"
echo "   $WEBHOOK_SECRET"
echo ""
echo "   Events (select these):"
echo "     ✓ Pull requests"
echo "     ✓ Pull request reviews"
echo "     ✓ Pull request review comments"
echo "     ✓ Issue comments"
echo "     ✓ Workflow runs"
echo ""
echo "   Active: ✓"
echo ""
echo "4. Click 'Add webhook'"
echo ""

# Step 4: Start webhook receiver
echo "Step 4: Starting webhook receiver..."
echo ""
echo "Run this command to start listening for webhooks:"
echo ""
echo "  python3 .claude/scripts/webhook-receiver.py"
echo ""
echo "Keep this terminal open. You should see events logged as they arrive."
echo ""

# Step 5: Test the webhook
echo "Step 5: Testing the webhook (optional)"
echo "======================================"
echo ""
echo "To test, go to GitHub webhook settings and click 'Recent Deliveries'."
echo "You should see successful (200) deliveries when you create/comment on a PR."
echo ""

echo "✅ Webhook setup complete!"
echo ""
echo "Summary:"
echo "  Secret file: ~/.claude/webhook-secret"
echo "  Receiver script: .claude/scripts/webhook-receiver.py"
echo "  Logs: .claude/logs/webhook.log"
echo ""
echo "Next: Start the receiver and configure GitHub webhook"
echo ""
