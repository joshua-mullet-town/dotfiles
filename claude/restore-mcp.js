const fs = require("fs");
const path = require("path");

const configPath = process.env.HOME + "/.claude.json";
const backupPath = path.join(__dirname, "mcp-servers.json");

// Read current config
const config = JSON.parse(fs.readFileSync(configPath, "utf8"));

// Read backup
const backup = JSON.parse(fs.readFileSync(backupPath, "utf8"));

// Restore global MCP servers
if (backup.global && Object.keys(backup.global).length > 0) {
  if (!config.projects) config.projects = {};
  if (!config.projects["*"]) config.projects["*"] = {};
  config.projects["*"].mcpServers = backup.global;
  console.log("Restored global MCP servers:", Object.keys(backup.global).length);
}

// Restore project-specific MCP servers
let projectCount = 0;
for (const [projPath, mcpServers] of Object.entries(backup.projects || {})) {
  if (!config.projects) config.projects = {};
  if (!config.projects[projPath]) config.projects[projPath] = {};
  config.projects[projPath].mcpServers = mcpServers;
  projectCount++;
}
console.log("Restored project configs:", projectCount);

// Write back
fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
console.log("Saved to:", configPath);
