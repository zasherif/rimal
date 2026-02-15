# RML RTL Editor (VS Code / Cursor extension)

This is a small **custom editor** (webview) that lets you edit `*.rml` files in **RTL**.

## Install (Cursor)

1. Copy this folder into Cursor extensions directory:

- `~/.cursor/extensions/rimal.rml-rtl-editor-0.0.1/`

2. Reload Cursor:

- Command Palette → **Developer: Reload Window**

3. (Optional) Make it the default editor for `.rml`:

Add to Cursor settings JSON:

```json
"workbench.editorAssociations": {
  "*.rml": "rimal.rmlRtlEditor"
}
```

## Install (VS Code)

Copy this folder into VS Code extensions directory:

- macOS/Linux: `~/.vscode/extensions/rimal.rml-rtl-editor-0.0.1/`

Then reload VS Code.

## Use

- Open a `.rml` file
- Right-click the tab → **Reopen Editor With...** → **RML RTL Editor**

Or run command:

- **RML: Reopen Active File in RTL Editor**

