// Minimal VS Code/Cursor extension:
// - Provides a dedicated RTL editor for *.rml using a webview custom editor.
// - Uses CustomEditorProvider (workspace.fs) for better Cursor compatibility.

const vscode = require("vscode");

class RmlCustomDocument {
  /**
   * @param {vscode.Uri} uri
   * @param {string} text
   */
  constructor(uri, text) {
    this.uri = uri;
    this._text = text;
    this._onDidDispose = new vscode.EventEmitter();
    this.onDidDispose = this._onDidDispose.event;
  }

  get text() {
    return this._text;
  }

  set text(v) {
    this._text = v;
  }

  dispose() {
    this._onDidDispose.fire();
    this._onDidDispose.dispose();
  }
}

class RmlRtlEditorProvider {
  static viewType = "rimal.rmlRtlEditor";

  /**
   * @param {vscode.ExtensionContext} context
   */
  constructor(context) {
    this._context = context;
    this._onDidChangeCustomDocument = new vscode.EventEmitter();
    this.onDidChangeCustomDocument = this._onDidChangeCustomDocument.event;
    /** @type {Map<string, vscode.WebviewPanel>} */
    this._panels = new Map();
  }

  /**
   * @param {vscode.Uri} uri
   * @param {{ backupId?: string }} _openContext
   * @param {vscode.CancellationToken} _token
   */
  async openCustomDocument(uri, _openContext, _token) {
    const data = await vscode.workspace.fs.readFile(uri);
    const text = new TextDecoder("utf-8").decode(data);
    return new RmlCustomDocument(uri, text);
  }

  /**
   * @param {RmlCustomDocument} document
   * @param {vscode.WebviewPanel} webviewPanel
   * @param {vscode.CancellationToken} _token
   */
  async resolveCustomEditor(document, webviewPanel, _token) {
    webviewPanel.webview.options = {
      enableScripts: true,
    };

    const updateWebview = () => {
      webviewPanel.webview.postMessage({
        type: "setText",
        text: document.text,
      });
    };

    this._panels.set(document.uri.toString(), webviewPanel);
    webviewPanel.onDidDispose(() => this._panels.delete(document.uri.toString()));

    webviewPanel.webview.html = this._getHtml(webviewPanel.webview, document.text);

    webviewPanel.webview.onDidReceiveMessage(async (msg) => {
      if (!msg || typeof msg.type !== "string") return;

      if (msg.type === "edit" && typeof msg.text === "string") {
        const newText = msg.text;
        if (newText === document.text) return;

        const oldText = document.text;
        document.text = newText;

        this._onDidChangeCustomDocument.fire({
          document,
          label: "Edit",
          undo: async () => {
            document.text = oldText;
            updateWebview();
          },
          redo: async () => {
            document.text = newText;
            updateWebview();
          },
        });
      }
    });

    // Initial sync (in case the doc changed between html set and load)
    updateWebview();
  }

  /**
   * @param {RmlCustomDocument} document
   * @param {vscode.CancellationToken} _token
   */
  async saveCustomDocument(document, _token) {
    const data = new TextEncoder().encode(document.text);
    await vscode.workspace.fs.writeFile(document.uri, data);
  }

  /**
   * @param {RmlCustomDocument} document
   * @param {vscode.Uri} destination
   * @param {vscode.CancellationToken} _token
   */
  async saveCustomDocumentAs(document, destination, _token) {
    const data = new TextEncoder().encode(document.text);
    await vscode.workspace.fs.writeFile(destination, data);
  }

  /**
   * @param {RmlCustomDocument} document
   * @param {vscode.CancellationToken} _token
   */
  async revertCustomDocument(document, _token) {
    const data = await vscode.workspace.fs.readFile(document.uri);
    document.text = new TextDecoder("utf-8").decode(data);
    const panel = this._panels.get(document.uri.toString());
    if (panel) {
      panel.webview.postMessage({ type: "setText", text: document.text });
    }
  }

  /**
   * @param {RmlCustomDocument} document
   * @param {{ destination: vscode.Uri }} context
   * @param {vscode.CancellationToken} _token
   */
  async backupCustomDocument(document, context, _token) {
    const data = new TextEncoder().encode(document.text);
    await vscode.workspace.fs.writeFile(context.destination, data);
    return {
      id: context.destination.toString(),
      delete: async () => {
        // Best-effort cleanup.
        try {
          await vscode.workspace.fs.delete(context.destination);
        } catch {
          // ignore
        }
      },
    };
  }

  /**
   * @param {vscode.Webview} webview
   * @param {string} initialText
   */
  _getHtml(webview, initialText) {
    const initialJson = JSON.stringify(initialText);
    const nonce = String(Date.now());

    // Use VS Code theme variables where possible.
    return `<!doctype html>
<html lang="ar">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>RML RTL Editor</title>
    <style>
      html, body {
        height: 100%;
        padding: 0;
        margin: 0;
        background: var(--vscode-editor-background);
        color: var(--vscode-editor-foreground);
        font-family: var(--vscode-editor-font-family);
        font-size: var(--vscode-editor-font-size);
      }
      .wrap {
        height: 100%;
        display: flex;
        flex-direction: column;
      }
      textarea {
        flex: 1;
        width: 100%;
        border: none;
        outline: none;
        resize: none;
        padding: 12px;
        box-sizing: border-box;
        background: var(--vscode-editor-background);
        color: var(--vscode-editor-foreground);
        font-family: var(--vscode-editor-font-family);
        font-size: var(--vscode-editor-font-size);
        line-height: 1.5;

        direction: rtl;
        unicode-bidi: plaintext;
        text-align: right;
        white-space: pre;
      }
      .hint {
        padding: 6px 12px;
        border-top: 1px solid var(--vscode-editorWidget-border);
        font-size: 12px;
        opacity: 0.85;
        direction: rtl;
        unicode-bidi: plaintext;
        text-align: right;
      }
      code {
        font-family: var(--vscode-editor-font-family);
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <textarea id="editor" spellcheck="false"></textarea>
      <div class="hint">افتح ملفات <code>.rml</code> بهذا المحرر عبر <code>Reopen Editor With...</code></div>
    </div>
    <script nonce="${nonce}">
      const vscode = acquireVsCodeApi();
      const editor = document.getElementById('editor');

      let applyingFromHost = false;
      let sendTimer = null;

      function sendEdit() {
        vscode.postMessage({ type: 'edit', text: editor.value });
      }

      editor.addEventListener('input', () => {
        if (applyingFromHost) return;
        if (sendTimer) clearTimeout(sendTimer);
        sendTimer = setTimeout(sendEdit, 120);
      });

      window.addEventListener('message', (event) => {
        const msg = event.data;
        if (!msg || msg.type !== 'setText' || typeof msg.text !== 'string') return;
        if (msg.text === editor.value) return;
        applyingFromHost = true;
        const selStart = editor.selectionStart;
        const selEnd = editor.selectionEnd;
        editor.value = msg.text;
        // Best effort: preserve selection
        editor.selectionStart = Math.min(selStart, editor.value.length);
        editor.selectionEnd = Math.min(selEnd, editor.value.length);
        applyingFromHost = false;
      });

      // Initial content
      editor.value = ${initialJson};
    </script>
  </body>
</html>`;
  }
}

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  const provider = new RmlRtlEditorProvider(context);
  context.subscriptions.push(
    vscode.window.registerCustomEditorProvider(RmlRtlEditorProvider.viewType, provider, {
      webviewOptions: { retainContextWhenHidden: true },
      supportsMultipleEditorsPerDocument: false,
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("rimal.rml.openRtlEditor", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
      const uri = editor.document.uri;
      await vscode.commands.executeCommand("vscode.openWith", uri, RmlRtlEditorProvider.viewType);
    })
  );
}

function deactivate() {}

module.exports = { activate, deactivate };

