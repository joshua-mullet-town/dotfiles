const fs = require("fs");
const path = require("path");

const config = JSON.parse(fs.readFileSync(process.env.HOME + "/.claude.json", "utf8"));

// Patterns to redact (API keys, tokens, secrets)
// These patterns match the key value only, preserving JSON structure
const SECRET_PATTERNS = [
  /sk_test_[A-Za-z0-9]+/g,
  /sk_live_[A-Za-z0-9]+/g,
  /rk_test_[A-Za-z0-9]+/g,
  /rk_live_[A-Za-z0-9]+/g,
  /whsec_[A-Za-z0-9]+/g,
];

function redactSecrets(obj) {
  const str = JSON.stringify(obj);
  let redacted = str;
  for (const pattern of SECRET_PATTERNS) {
    redacted = redacted.replace(pattern, "REDACTED");
  }
  return JSON.parse(redacted);
}

// Extract global MCP servers (user-level, not project-specific)
const globalMcp = config.projects?.["*"]?.mcpServers || {};

// Also grab any project-specific ones we want to preserve
const allMcp = { global: globalMcp, projects: {} };

// Find project-specific MCP servers
for (const [projPath, proj] of Object.entries(config.projects || {})) {
  if (projPath !== "*" && proj.mcpServers && Object.keys(proj.mcpServers).length > 0) {
    allMcp.projects[projPath] = proj.mcpServers;
  }
}

// Redact secrets before saving
const sanitized = redactSecrets(allMcp);

const outputPath = path.join(__dirname, "mcp-servers.json");
fs.writeFileSync(outputPath, JSON.stringify(sanitized, null, 2));
console.log("Exported MCP servers to:", outputPath);
console.log("Global servers:", Object.keys(globalMcp).length);
console.log("Project-specific configs:", Object.keys(allMcp.projects).length);
console.log("NOTE: Secrets have been redacted - restore will need manual re-entry of API keys");
