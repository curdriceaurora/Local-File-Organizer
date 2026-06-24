
#!/bin/bash

# 1. Set your Repo (Owner/RepoName)

REPO=“curdriceaurora/Local-File-Organizer" 

# 2. MacOS (BSD) compatible date calculation

SINCE=$(date -v-1m +%Y-%m-%d)

echo "Fetching PRs merged since $SINCE in $REPO..."

# 3. Get all PRs merged in the last month
# We use -L to set the limit and filter by date using jq
prs=$(gh pr list --repo "$REPO" \
    --state merged \
    --limit 100 \
    --json number,mergedAt \
    --jq ".[] | select(.mergedAt >= \"$SINCE\") | .number")

if [ -z "$prs" ]; then
    echo "No merged PRs found since $SINCE."
    exit 0
fi

# Count the PRs found
pr_count=$(echo "$prs" | wc -l | xargs)
echo "PRs found: $pr_count"
echo "-----------------------------------"

# 4. Iterate through each PR and fetch review comments
for pr in $prs; do
    echo "Processing PR #$pr..."
    
    gh pr view "$pr" --repo "$REPO" --json number,title,url,reviews --jq '
        "PR #\(.number): \(.title)\nURL: \(.url)\n" +
        (.reviews | map(
            "Reviewer: \(.author.login)\n" +
            (.comments | map("- [\(.path):\(.line)] \(.body)") | join("\n"))
        ) | join("\n---\n"))'
    
    echo -e "\n===================================\n"
done