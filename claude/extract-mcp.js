const fs = require("fs");
const path = require("path");
const os = require("os");

const HOME = os.homedir();
const configPath = path.join(HOME, ".claude.json");
const outputPath = path.join(__dirname, "mcp-servers.json");
const secretsPath = path.join(__dirname, "mcp-secrets.json");
const machineConfigPath = path.join(__dirname, "machine-config.json");

// --- Load machine config ---
let codeDir;
if (fs.existsSync(machineConfigPath)) {
  const machineConfig = JSON.parse(fs.readFileSync(machineConfigPath, "utf8"));
  codeDir = machineConfig.codeDir;
} else {
  // Auto-detect: check common locations
  const candidates = ["code", "repos", "projects", "src"].map(d => path.join(HOME, d));
  codeDir = candidates.find(d => fs.existsSync(d));
  if (!codeDir) {
    console.error("ERROR: Could not detect code directory.");
    console.error("Create claude/machine-config.json with: { \"codeDir\": \"/path/to/your/code\" }");
    process.exit(1);
  }
  // Save it for future runs
  fs.writeFileSync(machineConfigPath, JSON.stringify({ codeDir }, null, 2));
  console.log(`Auto-detected code directory: ${codeDir}`);
  console.log(`Saved to ${machineConfigPath}`);
}

// --- Patterns to extract secrets ---
const SECRET_PATTERNS = [
  { pattern: /sk_test_[A-Za-z0-9]+/g, name: "STRIPE_TEST_API_KEY" },
  { pattern: /sk_live_[A-Za-z0-9]+/g, name: "STRIPE_LIVE_API_KEY" },
  { pattern: /rk_test_[A-Za-z0-9]+/g, name: "STRIPE_TEST_RESTRICTED_KEY" },
  { pattern: /rk_live_[A-Za-z0-9]+/g, name: "STRIPE_LIVE_RESTRICTED_KEY" },
  { pattern: /whsec_[A-Za-z0-9]+/g, name: "STRIPE_WEBHOOK_SECRET" },
  { pattern: /xoxc-[A-Za-z0-9-]+/g, name: "SLACK_XOXC_TOKEN" },
  { pattern: /xoxd-[A-Za-z0-9%+-]+/g, name: "SLACK_XOXD_TOKEN" },
  { pattern: /ATATT3x[A-Za-z0-9_=+-]+/g, name: "JIRA_API_TOKEN" },
];

// Env keys whose values should always be treated as secrets
const SECRET_ENV_KEYS = [
  "JIRA_API_TOKEN", "JIRA_USERNAME",
  "LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY",
  "TWILIO_AUTH_TOKEN", "TWILIO_ACCOUNT_SID",
];

function extractSecrets(str) {
  const secrets = {};
  for (const { pattern, name } of SECRET_PATTERNS) {
    const matches = str.match(pattern);
    if (matches && matches.length > 0) {
      secrets[name] = matches[0];
      str = str.replace(pattern, "${" + name + "}");
    }
  }
  return { sanitized: str, secrets };
}

// --- Abstract machine-specific paths ---
// Order matters: replace more specific (codeDir) before less specific (HOME)
function abstractPaths(str) {
  // Replace code directory with ${CODE_DIR}
  str = str.split(codeDir).join("${CODE_DIR}");
  // Replace home directory with ${HOME} (catches ~/.worktrees, ~/.local, etc.)
  str = str.split(HOME).join("${HOME}");
  return str;
}

// --- Read .claude.json ---
const config = JSON.parse(fs.readFileSync(configPath, "utf8"));

// Extract global MCP servers
const globalMcp = config.mcpServers || {};

// Extract project-specific MCP servers
const allMcp = { global: globalMcp, projects: {} };
for (const [projPath, proj] of Object.entries(config.projects || {})) {
  if (projPath !== "*" && proj.mcpServers && Object.keys(proj.mcpServers).length > 0) {
    allMcp.projects[projPath] = proj.mcpServers;
  }
}

// --- Extract secrets from env values by key name ---
function extractEnvSecrets(obj) {
  const secrets = {};
  function walk(node) {
    if (!node || typeof node !== "object") return;
    if (node.env && typeof node.env === "object") {
      for (const [key, value] of Object.entries(node.env)) {
        if (SECRET_ENV_KEYS.includes(key) && value && !value.startsWith("${")) {
          secrets[key] = value;
          node.env[key] = "${" + key + "}";
        }
      }
    }
    for (const val of Object.values(node)) {
      walk(val);
    }
  }
  walk(obj);
  return secrets;
}

// --- Process: extract env secrets, abstract paths, then extract pattern secrets ---
const envSecrets = extractEnvSecrets(allMcp);
let jsonStr = JSON.stringify(allMcp, null, 2);
jsonStr = abstractPaths(jsonStr);
const { sanitized, secrets: patternSecrets } = extractSecrets(jsonStr);
const secrets = { ...envSecrets, ...patternSecrets };

// --- Write portable config (safe for git) ---
fs.writeFileSync(outputPath, sanitized);
console.log(`\nExported MCP servers to: ${outputPath}`);
console.log(`  Global servers: ${Object.keys(globalMcp).length}`);
console.log(`  Project configs: ${Object.keys(allMcp.projects).length}`);

// --- Write/merge secrets (gitignored) ---
if (Object.keys(secrets).length > 0) {
  let existingSecrets = {};
  if (fs.existsSync(secretsPath)) {
    existingSecrets = JSON.parse(fs.readFileSync(secretsPath, "utf8"));
  }
  const mergedSecrets = { ...existingSecrets, ...secrets };
  fs.writeFileSync(secretsPath, JSON.stringify(mergedSecrets, null, 2));
  console.log(`  Secrets found: ${Object.keys(secrets).join(", ")}`);
}

console.log(`\nFiles:`);
console.log(`  mcp-servers.json   - Portable config (paths use \${HOME} and \${CODE_DIR})`);
console.log(`  mcp-secrets.json   - GITIGNORED (actual API keys)`);
console.log(`  machine-config.json - GITIGNORED (this machine's code directory)`);
