const fs = require("fs");
const path = require("path");
const os = require("os");

const HOME = os.homedir();
const configPath = path.join(HOME, ".claude.json");
const backupPath = path.join(__dirname, "mcp-servers.json");
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
  fs.writeFileSync(machineConfigPath, JSON.stringify({ codeDir }, null, 2));
  console.log(`Auto-detected code directory: ${codeDir}`);
}

console.log(`Machine config: HOME=${HOME}, CODE_DIR=${codeDir}\n`);

// --- Read portable config ---
let backupStr = fs.readFileSync(backupPath, "utf8");

// --- Substitute machine-specific paths ---
// Order matters: replace ${CODE_DIR} before ${HOME} since CODE_DIR may contain HOME
backupStr = backupStr.split("${CODE_DIR}").join(codeDir);
backupStr = backupStr.split("${HOME}").join(HOME);

// --- Substitute secrets ---
if (fs.existsSync(secretsPath)) {
  const secrets = JSON.parse(fs.readFileSync(secretsPath, "utf8"));
  for (const [key, value] of Object.entries(secrets)) {
    backupStr = backupStr.replace(new RegExp("\\$\\{" + key + "\\}", "g"), value);
  }
  console.log(`Substituted secrets: ${Object.keys(secrets).join(", ")}`);
} else {
  console.log("WARNING: No mcp-secrets.json found - secret placeholders will remain!");
  console.log("Create mcp-secrets.json with your API keys to restore fully.\n");
}

const backup = JSON.parse(backupStr);

// --- Read existing .claude.json (preserve non-MCP settings) ---
let config = {};
if (fs.existsSync(configPath)) {
  config = JSON.parse(fs.readFileSync(configPath, "utf8"));
}

// --- Restore global MCP servers ---
if (backup.global && Object.keys(backup.global).length > 0) {
  config.mcpServers = { ...(config.mcpServers || {}), ...backup.global };
  console.log(`Restored global MCP servers: ${Object.keys(backup.global).length}`);
}

// --- Restore project-specific MCP servers ---
let projectCount = 0;
let skipped = 0;
for (const [projPath, mcpServers] of Object.entries(backup.projects || {})) {
  // Only restore projects whose directories exist on this machine
  if (!fs.existsSync(projPath)) {
    skipped++;
    continue;
  }
  if (!config.projects) config.projects = {};
  if (!config.projects[projPath]) config.projects[projPath] = {};
  config.projects[projPath].mcpServers = {
    ...(config.projects[projPath].mcpServers || {}),
    ...mcpServers,
  };
  projectCount++;
}
console.log(`Restored project configs: ${projectCount}`);
if (skipped > 0) {
  console.log(`Skipped ${skipped} project(s) (directory not found on this machine)`);
}

// --- Write back ---
fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
console.log(`\nSaved to: ${configPath}`);
