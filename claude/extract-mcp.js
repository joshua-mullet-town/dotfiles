const fs = require("fs");
const path = require("path");

const config = JSON.parse(fs.readFileSync(process.env.HOME + "/.claude.json", "utf8"));

// Patterns to extract secrets (API keys, tokens)
// Note: Slack tokens are workspace-specific, so we use generic names
const SECRET_PATTERNS = [
  { pattern: /sk_test_[A-Za-z0-9]+/g, name: "STRIPE_TEST_API_KEY" },
  { pattern: /sk_live_[A-Za-z0-9]+/g, name: "STRIPE_LIVE_API_KEY" },
  { pattern: /rk_test_[A-Za-z0-9]+/g, name: "STRIPE_TEST_RESTRICTED_KEY" },
  { pattern: /rk_live_[A-Za-z0-9]+/g, name: "STRIPE_LIVE_RESTRICTED_KEY" },
  { pattern: /whsec_[A-Za-z0-9]+/g, name: "STRIPE_WEBHOOK_SECRET" },
  { pattern: /xoxc-[A-Za-z0-9-]+/g, name: "SLACK_XOXC_TOKEN" },
  { pattern: /xoxd-[A-Za-z0-9%+-]+/g, name: "SLACK_XOXD_TOKEN" },
];

function extractAndReplaceSecrets(obj) {
  const secrets = {};
  let str = JSON.stringify(obj);

  for (const { pattern, name } of SECRET_PATTERNS) {
    const matches = str.match(pattern);
    if (matches && matches.length > 0) {
      // Store the first match (usually there's only one per type)
      secrets[name] = matches[0];
      // Replace all occurrences with env var placeholder
      str = str.replace(pattern, "${" + name + "}");
    }
  }

  return { sanitized: JSON.parse(str), secrets };
}

// Extract global MCP servers (user-level, at top of .claude.json)
const globalMcp = config.mcpServers || {};

// Also grab any project-specific ones we want to preserve
const allMcp = { global: globalMcp, projects: {} };

// Find project-specific MCP servers
for (const [projPath, proj] of Object.entries(config.projects || {})) {
  if (projPath !== "*" && proj.mcpServers && Object.keys(proj.mcpServers).length > 0) {
    allMcp.projects[projPath] = proj.mcpServers;
  }
}

// Extract secrets and replace with placeholders
const { sanitized, secrets } = extractAndReplaceSecrets(allMcp);

// Write the sanitized config (safe for git)
const outputPath = path.join(__dirname, "mcp-servers.json");
fs.writeFileSync(outputPath, JSON.stringify(sanitized, null, 2));

// Write secrets file (gitignored)
const secretsPath = path.join(__dirname, "mcp-secrets.json");
if (Object.keys(secrets).length > 0) {
  // Merge with existing secrets file if it exists
  let existingSecrets = {};
  if (fs.existsSync(secretsPath)) {
    existingSecrets = JSON.parse(fs.readFileSync(secretsPath, "utf8"));
  }
  const mergedSecrets = { ...existingSecrets, ...secrets };
  fs.writeFileSync(secretsPath, JSON.stringify(mergedSecrets, null, 2));
  console.log("Updated secrets file:", secretsPath);
  console.log("Secrets found:", Object.keys(secrets).join(", "));
}

console.log("Exported MCP servers to:", outputPath);
console.log("Global servers:", Object.keys(globalMcp).length);
console.log("Project-specific configs:", Object.keys(allMcp.projects).length);
console.log("\nFiles:");
console.log("  mcp-servers.json  - Safe for git (secrets replaced with ${VAR})");
console.log("  mcp-secrets.json  - GITIGNORED (contains actual secrets)");
