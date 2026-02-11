# NC Dev System - OpenClaw Telegram Integration

## Concept

Use OpenClaw (ClawdBot) as the messaging gateway so you can send a Telegram message to trigger NC Dev System builds and receive results back in the same conversation.

```
YOU (Telegram)
  │
  │  "Build a task management app. Here's the PRD: [paste or file]"
  │
  ▼
OpenClaw (Telegram Bot)
  │
  │  Receives message via Telethon/Telegram Bot API
  │  Routes to NC Dev System handler
  │
  ▼
NC Dev System (Claude Code)
  │
  │  Parses requirements
  │  Asks clarifying questions → sent back via Telegram
  │  Builds autonomously
  │  Tests everything
  │
  ▼
OpenClaw (Telegram Bot)
  │
  │  Sends results back to YOU on Telegram:
  │  - Repository URL
  │  - Screenshots (inline images)
  │  - Usage summary
  │  - Test results
  │
  ▼
YOU (Telegram)
  "Looks good, but can you change the color scheme to dark mode?"
  │
  ▼
NC Dev System processes modification request...
```

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    TELEGRAM                                │
│                                                          │
│  User ←──messages──→ OpenClaw Bot (@nc_dev_bot)          │
└──────────────┬───────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│                   OPENCLAW GATEWAY                        │
│                                                          │
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ Telegram Channel │  │ NC Dev Plugin                │  │
│  │ Adapter          │  │                              │  │
│  │                  │  │ - Detects "build" intent     │  │
│  │ Receives msgs    │──│ - Extracts requirements      │  │
│  │ Sends replies    │  │ - Forwards to Claude Code    │  │
│  │ Sends images     │  │ - Relays responses back      │  │
│  └─────────────────┘  └──────────────┬───────────────┘  │
└──────────────────────────────────────┼───────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────┐
│                  NC DEV SYSTEM                            │
│                (Claude Code Headless)                     │
│                                                          │
│  claude -p "Build from requirements: {text}"             │
│    --output-format stream-json                           │
│    --allowedTools "Read,Write,Edit,Bash,Glob,Grep,Task"  │
│                                                          │
│  Streams progress updates back to OpenClaw plugin        │
│  which relays them to Telegram                           │
└──────────────────────────────────────────────────────────┘
```

## OpenClaw Plugin: NC Dev Agent

OpenClaw uses a plugin architecture. Create an NC Dev plugin:

```
extensions/nc-dev-agent/
├── package.json
├── src/
│   ├── index.ts          # Plugin entry point
│   ├── intent.ts         # Detect build/status/modify intents
│   ├── handler.ts        # Handle build requests
│   ├── formatter.ts      # Format results for Telegram
│   └── session.ts        # Track active build sessions
└── README.md
```

### Plugin Implementation

```typescript
// extensions/nc-dev-agent/src/index.ts
import { Plugin, Message, Channel } from '@openclaw/sdk'
import { detectIntent } from './intent'
import { handleBuild, handleStatus, handleModify } from './handler'

export class NCDevPlugin implements Plugin {
  name = 'nc-dev-agent'
  description = 'Autonomous development agent - send requirements, receive built projects'

  async onMessage(message: Message, channel: Channel): Promise<void> {
    const intent = await detectIntent(message.text)

    switch (intent.type) {
      case 'build':
        await handleBuild(message, channel, intent.requirements)
        break
      case 'status':
        await handleStatus(message, channel)
        break
      case 'modify':
        await handleModify(message, channel, intent.modification)
        break
      default:
        // Not an NC Dev request, let other plugins handle
        return
    }
  }
}
```

### Intent Detection

```typescript
// extensions/nc-dev-agent/src/intent.ts

interface Intent {
  type: 'build' | 'status' | 'modify' | 'unknown'
  requirements?: string
  modification?: string
  confidence: number
}

export async function detectIntent(text: string): Promise<Intent> {
  const buildKeywords = ['build', 'create', 'develop', 'make', 'generate']
  const statusKeywords = ['status', 'progress', 'how is', 'update']
  const modifyKeywords = ['change', 'modify', 'update', 'fix', 'add']

  const lower = text.toLowerCase()

  // Check for build intent
  if (buildKeywords.some(k => lower.includes(k)) &&
      (lower.includes('app') || lower.includes('project') || lower.includes('system') ||
       lower.includes('prd') || lower.includes('requirements'))) {
    return { type: 'build', requirements: text, confidence: 0.9 }
  }

  // Check for status intent
  if (statusKeywords.some(k => lower.includes(k))) {
    return { type: 'status', confidence: 0.8 }
  }

  // Check for modify intent (only if active build exists)
  if (modifyKeywords.some(k => lower.includes(k))) {
    return { type: 'modify', modification: text, confidence: 0.7 }
  }

  return { type: 'unknown', confidence: 0 }
}
```

### Build Handler

```typescript
// extensions/nc-dev-agent/src/handler.ts
import { spawn } from 'child_process'
import { Message, Channel } from '@openclaw/sdk'
import { formatProgress, formatDelivery, formatScreenshots } from './formatter'
import { sessionStore } from './session'

export async function handleBuild(
  message: Message,
  channel: Channel,
  requirements: string
): Promise<void> {
  // Save requirements to temp file
  const reqPath = `/tmp/nc-dev-${Date.now()}/requirements.md`
  await fs.mkdir(path.dirname(reqPath), { recursive: true })
  await fs.writeFile(reqPath, requirements)

  // Acknowledge
  await channel.send('Starting NC Dev System build. I\'ll update you at each phase.')

  // Store session
  const sessionId = crypto.randomUUID()
  sessionStore.set(message.userId, {
    sessionId,
    status: 'building',
    startedAt: new Date(),
    reqPath
  })

  // Launch Claude Code headless
  const claude = spawn('claude', [
    '-p', `Build the project from requirements at ${reqPath} using NC Dev System pipeline. ` +
          `Report progress at each phase boundary. When done, output the delivery report as JSON.`,
    '--output-format', 'stream-json',
    '--allowedTools', 'Read,Write,Edit,Bash,Glob,Grep,Task',
    '--cwd', '/Users/nrupal/dev/yensi/dev/nc-dev-system'
  ])

  let currentPhase = ''

  claude.stdout.on('data', async (data) => {
    const lines = data.toString().split('\n').filter(Boolean)

    for (const line of lines) {
      try {
        const event = JSON.parse(line)

        // Detect phase changes and send Telegram updates
        if (event.type === 'assistant' && event.message?.content) {
          const text = typeof event.message.content === 'string'
            ? event.message.content
            : event.message.content.map(c => c.text || '').join('')

          // Check for phase markers
          const phaseMatch = text.match(/Phase (\d)\/6: (.+)/i)
          if (phaseMatch && phaseMatch[0] !== currentPhase) {
            currentPhase = phaseMatch[0]
            await channel.send(formatProgress(currentPhase, text))
          }

          // Check for questions
          if (text.includes('?') && text.includes('Before I build')) {
            await channel.send(text)  // Forward questions to user
          }

          // Check for delivery
          if (text.includes('Build complete') || text.includes('Repository:')) {
            await sendDelivery(channel, text)
          }
        }
      } catch {
        // Non-JSON output, ignore
      }
    }
  })

  claude.on('close', async (code) => {
    sessionStore.set(message.userId, { ...sessionStore.get(message.userId), status: 'done' })
    if (code !== 0) {
      await channel.send('Build encountered an issue. Check /status for details.')
    }
  })
}

async function sendDelivery(channel: Channel, deliveryText: string): Promise<void> {
  // Send text summary
  await channel.send(formatDelivery(deliveryText))

  // Send screenshot images
  const screenshotDir = '/path/to/project/docs/screenshots/desktop/'
  const screenshots = await fs.readdir(screenshotDir)

  for (const screenshot of screenshots.slice(0, 5)) {  // First 5 screenshots
    await channel.sendImage(
      path.join(screenshotDir, screenshot),
      screenshot.replace('.png', '').replace(/-/g, ' ')
    )
  }
}

export async function handleStatus(message: Message, channel: Channel): Promise<void> {
  const session = sessionStore.get(message.userId)
  if (!session) {
    await channel.send('No active build. Send me requirements to start a new build.')
    return
  }

  // Query Claude Code for current status
  const { execSync } = require('child_process')
  const status = execSync(
    'claude -p "Check NC Dev System build status. Return concise summary." --output-format json',
    { cwd: '/Users/nrupal/dev/yensi/dev/nc-dev-system' }
  )

  await channel.send(JSON.parse(status.toString()).result)
}

export async function handleModify(
  message: Message,
  channel: Channel,
  modification: string
): Promise<void> {
  const session = sessionStore.get(message.userId)
  if (!session || session.status !== 'done') {
    await channel.send('No completed build to modify. Wait for current build to finish first.')
    return
  }

  await channel.send(`Processing modification: "${modification}"`)

  // Resume Claude Code session with modification request
  const claude = spawn('claude', [
    '-p', `The user wants to modify the project: "${modification}". ` +
          `Apply the change, retest, and report back with updated screenshots.`,
    '--continue',
    '--output-format', 'stream-json',
    '--cwd', session.projectDir
  ])

  // ... handle streaming output same as build
}
```

### Message Formatting for Telegram

```typescript
// extensions/nc-dev-agent/src/formatter.ts

export function formatProgress(phase: string, details: string): string {
  const emojis: Record<string, string> = {
    '1': '🔍',  // Understanding
    '2': '🏗️',  // Scaffolding
    '3': '⚡',  // Building
    '4': '🧪',  // Testing
    '5': '🛡️',  // Hardening
    '6': '📦',  // Delivering
  }

  const phaseNum = phase.match(/Phase (\d)/)?.[1] || '0'
  const emoji = emojis[phaseNum] || '🔄'

  return `${emoji} **${phase}**\n${truncate(details, 500)}`
}

export function formatDelivery(text: string): string {
  return `✅ **Build Complete!**\n\n${text}\n\n` +
    `📸 Screenshots attached below. Review and let me know if you want changes.`
}

function truncate(text: string, maxLen: number): string {
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}
```

## Telegram Bot Setup

### Creating the Bot

1. Message @BotFather on Telegram
2. Create new bot: `/newbot`
3. Name: "NC Dev Agent" / Username: `nc_dev_agent_bot`
4. Save the bot token

### OpenClaw Configuration

```json5
// openclaw config
{
  "channels": {
    "telegram": {
      "enabled": true,
      "bot_token": "${TELEGRAM_BOT_TOKEN}",
      "allowed_users": ["your_telegram_user_id"]
    }
  },
  "plugins": {
    "nc-dev-agent": {
      "enabled": true,
      "claude_code_path": "/usr/local/bin/claude",
      "nc_dev_system_path": "/Users/nrupal/dev/yensi/dev/nc-dev-system",
      "max_concurrent_builds": 1,
      "progress_update_interval": "phase",  // "phase" or "minute"
      "max_screenshots_in_delivery": 5
    }
  }
}
```

## Conversation Flow Example

```
YOU: Build me a personal finance tracker. It should have:
     - Transaction tracking (income/expense)
     - Category management
     - Monthly budget setting
     - Dashboard with spending charts
     - CSV import for bank statements

BOT: 🔍 Starting NC Dev System. Analyzing your requirements...

     I have a few questions before building:

     1. Should transactions support multiple currencies or just one?
     2. Should the CSV import auto-categorize transactions?
     3. Do you want authentication or is this single-user?

YOU: Single currency (USD), yes auto-categorize, no auth needed.

BOT: 🏗️ Phase 2/6: Scaffolding project...
     ✓ Created repo: github.com/user/finance-tracker
     ✓ React 19 + FastAPI scaffold ready
     ✓ Mock layer generated

BOT: ⚡ Phase 3/6: Building features (3 builders parallel)...
     Builder 1: Transaction CRUD + categories
     Builder 2: Budget management + dashboard
     Builder 3: CSV import + auto-categorization

BOT: ⚡ Feature update:
     ✓ Transaction CRUD — done
     ✓ Budget management — done
     ◐ CSV import — in progress

BOT: 🧪 Phase 4/6: Testing & verification...
     ✓ 28/29 tests passing
     ⚠ Dashboard chart not rendering on mobile — fixing...
     ✓ Fixed and retested — all passing

BOT: 🛡️ Phase 5/6: Hardening...
     ✓ Error handling added
     ✓ Responsive verified
     ✓ Accessibility: WCAG AA

BOT: 📦 **Build Complete!**

     **Repository**: https://github.com/user/finance-tracker

     **Quick Start**:
     ```
     git clone https://github.com/user/finance-tracker
     cd finance-tracker
     docker compose up -d
     open http://localhost:23000
     ```

     **Features Built**: 5/5
     **Tests**: 29/29 passing (82% coverage)
     **All mocks active** — set MOCK_APIS=false for production

     📸 Screenshots:

BOT: [Image: Dashboard with spending chart]
     Dashboard — shows monthly spending by category

BOT: [Image: Transaction list]
     Transaction List — add, edit, delete with search

BOT: [Image: CSV Import]
     CSV Import — drag-and-drop with auto-categorization

BOT: [Image: Budget Settings]
     Budget Settings — set monthly limits per category

BOT: [Image: Mobile view]
     Mobile responsive view

YOU: Looks great! Can you change the color scheme to use dark mode by default?

BOT: 🔄 Processing modification...
     Updating theme to dark mode default...
     ✓ Dark mode applied across all pages
     ✓ Retested — all passing
     📸 Updated screenshots:

BOT: [Image: Dashboard dark mode]
     Dashboard — dark mode

YOU: Perfect, ship it! 🚀
```

## Handling File Attachments

For requirements documents sent as file attachments on Telegram:

```typescript
async onFileMessage(message: Message, channel: Channel): Promise<void> {
  if (message.file?.mimeType === 'text/markdown' ||
      message.file?.name?.endsWith('.md')) {
    // Download and save the file
    const content = await channel.downloadFile(message.file.id)
    const reqPath = `/tmp/nc-dev-${Date.now()}/requirements.md`
    await fs.writeFile(reqPath, content)

    await channel.send('Received requirements document. Starting build...')
    await handleBuild(message, channel, content)
  }
}
```

## Security Considerations

1. **User allowlist**: Only authorized Telegram user IDs can trigger builds
2. **Rate limiting**: Maximum 1 concurrent build per user
3. **Resource limits**: Builds auto-terminate after 8 hours
4. **No secrets in messages**: API keys never sent via Telegram
5. **Sandboxed execution**: Builds run in Docker containers
6. **Audit log**: All build requests logged with user ID and timestamp
