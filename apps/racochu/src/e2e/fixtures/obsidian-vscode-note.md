---
Created: 2023-05-09T19:04:00
tags:
  - it-notes
  - it-notes/engineering
  - notes
Kind: note
Type: projects
Project: it
Updated: 2026-03-25T10:13:05+01:00
---

## Appearance
- Font = CMD + "+"
### File Nesting

- **File nesting**

- **user settings.json**

	```json
	{
	"workbench.startupEditor": "none",
	"workbench.editor.openPositioning": "right",
	"workbench.colorTheme": "Ra Spring",
	"svelte.enable-ts-plugin": true,
	"files.autoSave": "onFocusChange",
	"editor.fontFamily": "Fira Code",
	"editor.fontSize": 17,
	"editor.tabSize": 2,
	"terminal.integrated.fontSize": 14,
	"window.zoomLevel": 0.1,
	"[Log]": {
	  "editor.fontSize": 14
	},
	"editor.fontVariations": false,
	"editor.fontLigatures": true,
	"editor.fontWeight": "normal",
	"editor.codeActionsOnSave": {
	  "source.fixAll.eslint": "explicit"
	},
	"interactiveSession.editor.fontSize": 16,
	"markdown.preview.fontSize": 16,
	"debug.console.fontSize": 16,
	"workbench.iconTheme": "vscode-great-icons",
	"git.confirmSync": false,
	"eslint.format.enable": true,
	"eslint.validate": ["javascript", "typescript"],
	"[typescript]": {
	  "editor.tabSize": 2,
	  "editor.defaultFormatter": "vscode.typescript-language-features"
	},
	"explorer.confirmDragAndDrop": false,
	"conventionalCommits.gitmoji": false,
	"[typescriptreact]": {
	  "editor.defaultFormatter": "dbaeumer.vscode-eslint"
	},
	"cmake.configureOnOpen": true,
	"editor.detectIndentation": false,
	"typescript.enablePromptUseWorkspaceTsdk": true
	}
	```

## Extensions
- Essential extensions for development workflow
- ESLint, Prettier, GitLens, Todo Tree

## Keyboard Shortcuts
- Custom keybindings for productivity
- Use "Preferences: Open Keyboard Shortcuts (JSON)" to manage

## Profiles
- Separate profiles for different projects
- Use "Manage > Profiles" to switch

## Terminal
- Integrated terminal settings
- Default profile: zsh
- Font size: 14

## Debugging
- Node.js debugging configuration
- Launch configurations in .vscode/launch.json
