const vscode = require("vscode");
const { execFile, spawn } = require("child_process");
const http = require("http");
const path = require("path");

let outputChannel;
let statusBar;
let healthTimer;
let guardProcess;
let dashboardPanel;
let replayPanel;

function activate(context) {
  outputChannel = vscode.window.createOutputChannel("Agent Loop Guard");
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBar.command = "agentLoopGuard.showStatus";
  statusBar.show();

  context.subscriptions.push(
    outputChannel,
    statusBar,
    vscode.commands.registerCommand("agentLoopGuard.start", () => startGuard()),
    vscode.commands.registerCommand("agentLoopGuard.stop", () => stopGuard()),
    vscode.commands.registerCommand("agentLoopGuard.restart", () => restartGuard()),
    vscode.commands.registerCommand("agentLoopGuard.openDashboard", () => openDashboard()),
    vscode.commands.registerCommand("agentLoopGuard.openReplay", () => openReplay()),
    vscode.commands.registerCommand("agentLoopGuard.showStatus", () => showStatus()),
    vscode.commands.registerCommand("agentLoopGuard.copyOpenAIBaseUrl", () => copyOpenAIBaseUrl()),
    vscode.commands.registerCommand("agentLoopGuard.copyAnthropicBaseUrl", () =>
      copyAnthropicBaseUrl()
    ),
    vscode.commands.registerCommand("agentLoopGuard.copyAgentEnv", () => copyAgentEnv()),
    vscode.commands.registerCommand("agentLoopGuard.installRuntime", () => installRuntime()),
    vscode.commands.registerCommand("agentLoopGuard.setupWorkspace", () => setupWorkspace()),
    vscode.window.registerWebviewViewProvider(
      "agentLoopGuard.guardView",
      new DashboardViewProvider(() => readConfig().baseUrl, "Guard")
    ),
    vscode.window.registerWebviewViewProvider(
      "agentLoopGuard.replayView",
      new DashboardViewProvider(() => `${readConfig().baseUrl}/replay`, "Replay")
    )
  );

  healthTimer = setInterval(() => {
    void updateStatusBar();
  }, 30000);
  context.subscriptions.push({
    dispose: () => clearInterval(healthTimer)
  });

  void ensureRuntime({ silent: true });
  void updateStatusBar();

  if (readConfig().autoStart) {
    void startGuard({ silent: true });
  }
}

class DashboardViewProvider {
  constructor(url, title) {
    this.url = url;
    this.title = title;
  }

  resolveWebviewView(view) {
    view.webview.options = { enableScripts: true };
    view.webview.html = dashboardHtml(this.url(), this.title);
  }
}

async function commandExists(command) {
  return new Promise((resolve) => {
    const probe = process.platform === "win32" ? "where" : "which";
    execFile(probe, [command], { windowsHide: true }, (error) => resolve(!error));
  });
}

async function ensureRuntime(options = {}) {
  const config = readConfig();
  if (config.startMode === "source" || (await commandExists(config.cliCommand))) {
    return true;
  }
  if (options.silent) {
    statusBar.text = "$(warning) ALG missing";
    statusBar.tooltip = "Agent Loop Guard runtime is not installed";
    return false;
  }
  const choice = await vscode.window.showWarningMessage(
    "Agent Loop Guard runtime was not found.",
    "Install Runtime",
    "Open Instructions"
  );
  if (choice === "Install Runtime") {
    await installRuntime();
  } else if (choice === "Open Instructions") {
    await vscode.env.openExternal(vscode.Uri.parse("https://github.com/RIMUMURUDEV/agent-loop-guard/blob/main/docs/getting-started/installation.md"));
  }
  return false;
}

async function installRuntime() {
  const method = await vscode.window.showQuickPick(
    [
      { label: "pipx", description: "Recommended isolated installation", command: "pipx install git+https://github.com/RIMUMURUDEV/agent-loop-guard.git" },
      { label: "uv tool", description: "Install with uv", command: "uv tool install git+https://github.com/RIMUMURUDEV/agent-loop-guard.git" },
      { label: "pip", description: "Install into the active Python environment", command: "python -m pip install git+https://github.com/RIMUMURUDEV/agent-loop-guard.git" }
    ],
    { placeHolder: "Choose how to install the local runtime" }
  );
  if (!method) {
    return;
  }
  const terminal = vscode.window.createTerminal({ name: "Agent Loop Guard Setup" });
  terminal.show();
  terminal.sendText(method.command, true);
}

async function setupWorkspace() {
  if (!(await ensureRuntime())) {
    return;
  }
  const root = firstWorkspaceFolder();
  if (!root) {
    void vscode.window.showErrorMessage("Open a workspace before running Agent Loop Guard setup.");
    return;
  }
  const config = readConfig();
  const source = resolvePath(config.sourcePath) || root;
  const terminal = vscode.window.createTerminal({
    name: "Agent Loop Guard Setup",
    cwd: config.startMode === "source" ? source : root
  });
  terminal.show();
  if (config.startMode === "source") {
    terminal.sendText(
      `${quoteForShell(config.pythonPath)} -m app.cli setup --path ${quoteForShell(root)}`,
      true
    );
    outputChannel.appendLine(`[setup:source] ${source}`);
  } else {
    terminal.sendText(`${config.cliCommand} setup --path ${quoteForShell(root)}`, true);
  }
}

function deactivate() {
  if (readConfig().stopOnDeactivate && guardProcess) {
    killProcessTree(guardProcess);
  }
}

function readConfig() {
  const config = vscode.workspace.getConfiguration("agentLoopGuard");
  const host = config.get("host", "127.0.0.1");
  const port = Number(config.get("port", 8787));
  return {
    autoStart: config.get("autoStart", false),
    openDashboardOnStart: config.get("openDashboardOnStart", true),
    stopOnDeactivate: config.get("stopOnDeactivate", true),
    startMode: config.get("startMode", "cli"),
    cliCommand: config.get("cliCommand", "alg"),
    pythonPath: config.get("pythonPath", "python"),
    sourcePath: config.get("sourcePath", ""),
    configPath: config.get("configPath", ""),
    host,
    port,
    gatewayKey: config.get("gatewayKey", "alg_demo_key"),
    environment: config.get("environment", {}),
    baseUrl: `http://${host}:${port}`,
    openAIBaseUrl: `http://${host}:${port}/v1`,
    anthropicBaseUrl: `http://${host}:${port}`
  };
}

function firstWorkspaceFolder() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  return folder?.uri.fsPath;
}

function resolvePath(value) {
  if (!value) {
    return "";
  }
  if (path.isAbsolute(value)) {
    return value;
  }
  const root = firstWorkspaceFolder();
  return root ? path.join(root, value) : value;
}

function buildLaunchConfig() {
  const config = readConfig();
  const configPath = resolvePath(config.configPath);
  const args = [];
  let command;
  let cwd;

  if (config.startMode === "source") {
    command = config.pythonPath;
    cwd = resolvePath(config.sourcePath) || firstWorkspaceFolder();
    if (!cwd) {
      throw new Error("Set agentLoopGuard.sourcePath or open an Agent Loop Guard workspace.");
    }
    args.push("-m", "app.cli", "run");
  } else {
    command = config.cliCommand;
    cwd = firstWorkspaceFolder();
    args.push("run");
  }

  if (configPath) {
    args.push("--config", configPath);
  }
  args.push("--host", config.host, "--port", String(config.port));

  const extraEnv = {};
  for (const [key, value] of Object.entries(config.environment || {})) {
    extraEnv[key] = String(value);
  }

  return {
    command,
    args,
    cwd,
    env: {
      ...process.env,
      ALG_GATEWAY_KEY: config.gatewayKey,
      ALG_HOST: config.host,
      ALG_PORT: String(config.port),
      ...(configPath ? { ALG_CONFIG: configPath } : {}),
      ...extraEnv
    }
  };
}

async function startGuard(options = {}) {
  if (!(await ensureRuntime(options))) {
    return;
  }
  const config = readConfig();
  const existingHealth = await fetchHealth(config);
  if (existingHealth.ok) {
    await updateStatusBar(existingHealth);
    if (!options.silent) {
      void vscode.window.showInformationMessage(`Agent Loop Guard is already running at ${config.baseUrl}.`);
    }
    return;
  }

  if (guardProcess) {
    if (!options.silent) {
      void vscode.window.showInformationMessage("Agent Loop Guard is starting.");
    }
    return;
  }

  let launch;
  try {
    launch = buildLaunchConfig();
  } catch (error) {
    void vscode.window.showErrorMessage(error.message);
    return;
  }

  outputChannel.appendLine(`[start] ${formatCommand(launch.command, launch.args)}`);
  if (launch.cwd) {
    outputChannel.appendLine(`[cwd] ${launch.cwd}`);
  }

  guardProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: launch.env,
    shell: process.platform === "win32",
    windowsHide: true
  });

  guardProcess.stdout?.on("data", (chunk) => {
    outputChannel.append(chunk.toString());
  });
  guardProcess.stderr?.on("data", (chunk) => {
    outputChannel.append(chunk.toString());
  });
  guardProcess.on("error", (error) => {
    outputChannel.appendLine(`[error] ${error.message}`);
    guardProcess = undefined;
    void updateStatusBar();
    void vscode.window.showErrorMessage(`Agent Loop Guard failed to start: ${error.message}`);
  });
  guardProcess.on("exit", (code, signal) => {
    outputChannel.appendLine(`[exit] code=${code ?? "null"} signal=${signal ?? "null"}`);
    guardProcess = undefined;
    void updateStatusBar();
  });

  const healthy = await waitForHealth(config, 30000);
  if (!healthy) {
    outputChannel.show(true);
    void vscode.window.showErrorMessage(
      "Agent Loop Guard did not become healthy. Check the Agent Loop Guard output."
    );
    return;
  }

  await updateStatusBar();
  if (!options.silent) {
    void vscode.window.showInformationMessage(`Agent Loop Guard is running at ${config.baseUrl}.`);
  }
  if (config.openDashboardOnStart) {
    await openDashboard();
  }
}

async function stopGuard() {
  if (!guardProcess) {
    const config = readConfig();
    const health = await fetchHealth(config);
    if (health.ok) {
      void vscode.window.showWarningMessage(
        "Agent Loop Guard is running, but it was not started by this VS Code extension."
      );
    } else {
      void vscode.window.showInformationMessage("Agent Loop Guard is not running.");
    }
    await updateStatusBar(health);
    return;
  }

  const processToStop = guardProcess;
  guardProcess = undefined;
  killProcessTree(processToStop);
  outputChannel.appendLine("[stop] requested");
  await sleep(700);
  await updateStatusBar();
}

async function restartGuard() {
  await stopGuard();
  await startGuard();
}

async function openDashboard() {
  const config = readConfig();
  const health = await fetchHealth(config);
  if (!health.ok) {
    const choice = await vscode.window.showWarningMessage(
      "Agent Loop Guard is not running.",
      "Start Guard",
      "Open Anyway"
    );
    if (choice === "Start Guard") {
      await startGuard();
      return;
    }
    if (choice !== "Open Anyway") {
      return;
    }
  }

  if (dashboardPanel) {
    dashboardPanel.reveal(vscode.ViewColumn.One);
  } else {
    dashboardPanel = vscode.window.createWebviewPanel(
      "agentLoopGuardDashboard",
      "Agent Loop Guard",
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true
      }
    );
    dashboardPanel.onDidDispose(() => {
      dashboardPanel = undefined;
    });
  }
  dashboardPanel.webview.html = dashboardHtml(config.baseUrl);
}

async function openReplay() {
  const config = readConfig();
  const health = await fetchHealth(config);
  if (!health.ok) {
    const choice = await vscode.window.showWarningMessage(
      "Agent Loop Guard is not running.",
      "Start Guard",
      "Open Anyway"
    );
    if (choice === "Start Guard") {
      await startGuard();
      return;
    }
    if (choice !== "Open Anyway") {
      return;
    }
  }

  if (replayPanel) {
    replayPanel.reveal(vscode.ViewColumn.One);
  } else {
    replayPanel = vscode.window.createWebviewPanel(
      "agentLoopGuardReplay",
      "Agent Loop Guard Replay",
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true
      }
    );
    replayPanel.onDidDispose(() => {
      replayPanel = undefined;
    });
  }
  replayPanel.webview.html = dashboardHtml(`${config.baseUrl}/replay`);
}

async function showStatus() {
  const config = readConfig();
  const health = await fetchHealth(config);
  await updateStatusBar(health);

  if (!health.ok) {
    const choice = await vscode.window.showInformationMessage(
      `Agent Loop Guard is offline at ${config.baseUrl}.`,
      "Start Guard",
      "Show Output"
    );
    if (choice === "Start Guard") {
      await startGuard();
    } else if (choice === "Show Output") {
      outputChannel.show(true);
    }
    return;
  }

  const stats = health.data?.stats || {};
  const message = `Agent Loop Guard is running. Sessions: ${stats.sessions ?? 0}, requests: ${
    stats.requests ?? 0
  }, flags: ${stats.flags ?? 0}, blocks: ${stats.blocks ?? 0}.`;
  const choice = await vscode.window.showInformationMessage(
    message,
    "Open Dashboard",
    "Open Replay",
    "Copy OpenAI URL",
    "Copy Env",
    "Stop"
  );
  if (choice === "Open Dashboard") {
    await openDashboard();
  } else if (choice === "Open Replay") {
    await openReplay();
  } else if (choice === "Copy OpenAI URL") {
    await copyOpenAIBaseUrl();
  } else if (choice === "Copy Env") {
    await copyAgentEnv();
  } else if (choice === "Stop") {
    await stopGuard();
  }
}

async function copyOpenAIBaseUrl() {
  const config = readConfig();
  await vscode.env.clipboard.writeText(config.openAIBaseUrl);
  void vscode.window.showInformationMessage(`Copied ${config.openAIBaseUrl}`);
}

async function copyAnthropicBaseUrl() {
  const config = readConfig();
  await vscode.env.clipboard.writeText(config.anthropicBaseUrl);
  void vscode.window.showInformationMessage(`Copied ${config.anthropicBaseUrl}`);
}

async function copyAgentEnv() {
  const config = readConfig();
  const snippet = [
    `ALG_GATEWAY_KEY=${config.gatewayKey}`,
    `OPENAI_BASE_URL=${config.openAIBaseUrl}`,
    `ANTHROPIC_BASE_URL=${config.anthropicBaseUrl}`,
    `ANTHROPIC_AUTH_TOKEN=${config.gatewayKey}`
  ].join("\n");
  await vscode.env.clipboard.writeText(snippet);
  void vscode.window.showInformationMessage("Copied Agent Loop Guard environment.");
}

async function updateStatusBar(knownHealth) {
  const config = readConfig();
  const health = knownHealth || (await fetchHealth(config));
  if (health.ok) {
    const stats = health.data?.stats || {};
    statusBar.text = "$(shield) ALG on";
    statusBar.tooltip = `Agent Loop Guard: ${config.baseUrl}\nRequests: ${
      stats.requests ?? 0
    }\nFlags: ${stats.flags ?? 0}\nBlocks: ${stats.blocks ?? 0}`;
    statusBar.backgroundColor = undefined;
  } else {
    statusBar.text = "$(shield) ALG off";
    statusBar.tooltip = `Agent Loop Guard is offline at ${config.baseUrl}`;
    statusBar.backgroundColor = undefined;
  }
}

async function fetchHealth(config) {
  try {
    const response = await requestJson(`${config.baseUrl}/api/health`, 1200);
    if (response.statusCode !== 200) {
      return { ok: false, statusCode: response.statusCode };
    }
    const data = JSON.parse(response.body || "{}");
    return { ok: data.ok === true, data, statusCode: response.statusCode };
  } catch (error) {
    return { ok: false, error };
  }
}

async function waitForHealth(config, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const health = await fetchHealth(config);
    if (health.ok) {
      return true;
    }
    await sleep(500);
  }
  return false;
}

function requestJson(url, timeoutMs) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const request = http.request(
      {
        method: "GET",
        hostname: target.hostname,
        port: target.port,
        path: `${target.pathname}${target.search}`,
        timeout: timeoutMs
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          resolve({
            statusCode: response.statusCode,
            body: Buffer.concat(chunks).toString("utf8")
          });
        });
      }
    );
    request.on("timeout", () => {
      request.destroy(new Error("request timed out"));
    });
    request.on("error", reject);
    request.end();
  });
}

function killProcessTree(childProcess) {
  if (process.platform === "win32") {
    execFile("taskkill", ["/pid", String(childProcess.pid), "/T", "/F"], (error) => {
      if (error) {
        outputChannel.appendLine(`[stop:error] ${error.message}`);
      }
    });
    return;
  }
  childProcess.kill("SIGTERM");
}

function dashboardHtml(url, title = "Agent Loop Guard") {
  const escapedUrl = escapeHtml(url);
  const origin = escapeHtml(new URL(url).origin);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta
    http-equiv="Content-Security-Policy"
    content="default-src 'none'; frame-src ${origin}; style-src 'unsafe-inline';"
  >
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    html, body, iframe {
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      border: 0;
      background: #0f172a;
    }
  </style>
  <title>${escapeHtml(title)}</title>
</head>
<body>
  <iframe title="Agent Loop Guard Dashboard" src="${escapedUrl}"></iframe>
</body>
</html>`;
}

function quoteForShell(value) {
  return `"${String(value).replace(/"/g, '\\"')}"`;
}

function formatCommand(command, args) {
  return [command, ...args].map(quoteForDisplay).join(" ");
}

function quoteForDisplay(value) {
  if (!/\s/.test(value)) {
    return value;
  }
  return `"${value.replace(/"/g, '\\"')}"`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

module.exports = {
  activate,
  deactivate
};
