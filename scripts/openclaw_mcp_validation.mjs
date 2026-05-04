import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

const workspaceRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const openclawRoot = process.env.OPENCLAW_ROOT;
if (!openclawRoot) {
  throw new Error("OPENCLAW_ROOT is required");
}
const { s: runCliAgent } = await import(`${openclawRoot}/dist/send-policy-BmMecujf.js`);

const tmpRoot = path.join(workspaceRoot, ".tmp", "openclaw-mcp-validation");
const tempHome = path.join(tmpRoot, "home");
const sessionFile = path.join(tmpRoot, "session.jsonl");
const backendScriptPath = path.join(tmpRoot, "fake-claude-wecom-mcp.mjs");
const pluginRoot = path.join(tempHome, ".openclaw", "extensions", "wecom-mcp");
const workspaceDir = path.join(tmpRoot, "workspace");

const mcpUrl = process.env.OPENCLAW_MCP_URL ?? "http://127.0.0.1:5001/mcp";
const mcpToken = process.env.OPENCLAW_MCP_BEARER_TOKEN;
if (!mcpToken) {
  throw new Error("OPENCLAW_MCP_BEARER_TOKEN is required");
}

async function writeFile(filePath, content, mode = 0o644) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, content, { encoding: "utf-8", mode });
}

async function writeBackendScript() {
  const content = `#!/usr/bin/env node
import fs from "node:fs/promises";
import { randomUUID } from "node:crypto";

function readArg(name) {
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i] ?? "";
    if (arg === name) return args[i + 1];
    if (arg.startsWith(name + "=")) return arg.slice(name.length + 1);
  }
  return undefined;
}

async function main() {
  const mcpConfigPath = readArg("--mcp-config");
  if (!mcpConfigPath) {
    throw new Error("missing --mcp-config");
  }
  const raw = JSON.parse(await fs.readFile(mcpConfigPath, "utf-8"));
  const servers = raw?.mcpServers ?? raw?.servers ?? {};
  const server = servers.wecomScrm ?? Object.values(servers)[0];
  if (!server || typeof server !== "object" || typeof server.url !== "string") {
    throw new Error("missing wecomScrm MCP server");
  }

  const requestInit = server.requestInit && typeof server.requestInit === "object"
    ? server.requestInit
    : { headers: server.headers && typeof server.headers === "object" ? server.headers : {} };
  const headers = {
    "Content-Type": "application/json",
    ...(requestInit.headers ?? {}),
  };
  let rpcId = 1;

  async function rpc(method, params = {}) {
    const res = await fetch(server.url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: rpcId++,
        method,
        params,
      }),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      throw new Error(JSON.stringify({ httpStatus: res.status, data }));
    }
    return data.result;
  }

  await rpc("initialize", {
    protocolVersion: "2025-03-26",
    capabilities: {},
    clientInfo: { name: "openclaw-wecom-mcp-check", version: "1.0.0" },
  });

  const toolsResult = await rpc("tools/list", {});
  const toolNames = (toolsResult.tools ?? []).map((tool) => tool.name).sort();

  const pending = await rpc("tools/call", {
    name: "get_pending_message_batches",
    arguments: { limit: 1, cursor: "" },
  });
  const pendingText = pending.content?.find((entry) => entry?.type === "text")?.text ?? "{}";
  const pendingData = JSON.parse(pendingText);
  const firstBatch = pendingData.items?.[0];

  let batchData = null;
  let contactData = null;
  let recentData = null;
  let ackData = null;

  if (firstBatch?.id) {
    const batch = await rpc("tools/call", {
      name: "get_message_batch",
      arguments: { batch_id: firstBatch.id, limit: 20, cursor: "" },
    });
    const batchText = batch.content.find((entry) => entry?.type === "text")?.text ?? "{}";
    batchData = JSON.parse(batchText);

    const externalUserId = batchData.messages?.find((item) => typeof item?.external_userid === "string" && item.external_userid)?.external_userid ?? "";

    if (externalUserId) {
      const contact = await rpc("tools/call", {
        name: "get_contact",
        arguments: { external_userid: externalUserId },
      });
      const contactText = contact.content.find((entry) => entry?.type === "text")?.text ?? "{}";
      contactData = JSON.parse(contactText);

      const recent = await rpc("tools/call", {
        name: "get_recent_messages",
        arguments: { external_userid: externalUserId, limit: 3, chat_type: "" },
      });
      const recentText = recent.content.find((entry) => entry?.type === "text")?.text ?? "{}";
      recentData = JSON.parse(recentText);
    }

    const ack = await rpc("tools/call", {
      name: "ack_message_batch",
      arguments: { batch_id: firstBatch.id, ack_note: "openclaw-validation", acked_by: "openclaw" },
    });
    const ackText = ack.content.find((entry) => entry?.type === "text")?.text ?? "{}";
    ackData = JSON.parse(ackText);
  }

  const payload = {
    mcp_url: server.url,
    auth_mode: "bearer",
    tools: toolNames,
    pending: pendingData,
    batch: batchData,
    contact: contactData,
    recent: recentData,
    ack: ackData,
  };

  process.stdout.write(JSON.stringify({
    session_id: readArg("--session-id") ?? randomUUID(),
    message: JSON.stringify(payload),
  }) + "\\n");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
`;
  await writeFile(backendScriptPath, content, 0o755);
}

async function writePluginBundle() {
  await writeFile(
    path.join(pluginRoot, ".claude-plugin", "plugin.json"),
    `${JSON.stringify({ name: "wecom-mcp" }, null, 2)}\n`,
  );
  await writeFile(
    path.join(pluginRoot, ".mcp.json"),
    `${JSON.stringify(
      {
        mcpServers: {
          wecomScrm: {
            transport: "streamable-http",
            url: mcpUrl,
            requestInit: {
              headers: {
                Authorization: `Bearer ${mcpToken}`,
              },
            },
          },
        },
      },
      null,
      2,
    )}\n`,
  );
}

async function main() {
  await fs.rm(tmpRoot, { recursive: true, force: true });
  await fs.mkdir(workspaceDir, { recursive: true });
  await writeBackendScript();
  await writePluginBundle();

  const originalHome = process.env.HOME;
  process.env.HOME = tempHome;

  try {
    const result = await runCliAgent({
      sessionId: "session:openclaw-mcp-validation",
      sessionFile,
      workspaceDir,
      config: {
        agents: {
          defaults: {
            workspace: workspaceDir,
            cliBackends: {
              "claude-cli": {
                command: "node",
                args: [backendScriptPath],
                clearEnv: [],
              },
            },
          },
        },
        plugins: {
          entries: {
            "wecom-mcp": { enabled: true },
          },
        },
      },
      prompt: "Connect to the configured MCP server and validate the tool chain.",
      provider: "claude-cli",
      model: "wecom-mcp-validation",
      timeoutMs: 30000,
      runId: "openclaw-mcp-validation",
    });

    const text = result.payloads?.find((item) => typeof item?.text === "string")?.text ?? "";
    if (!text) {
      throw new Error("OpenClaw validation returned empty payload");
    }
    console.log(text);
  } finally {
    process.env.HOME = originalHome;
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
