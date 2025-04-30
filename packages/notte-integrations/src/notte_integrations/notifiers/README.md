# Notte Notifiers

This guide explains how to set up notification services for Notte using Discord and Slack integrations.

## Table of Contents
- [Overview](#overview)
- [Slack Integration](#slack-integration)
  - [Creating a Slack App](#creating-a-slack-app)
  - [Getting the Required Credentials](#getting-the-slack-credentials)
  - [Configuration](#slack-configuration)
- [Discord Integration](#discord-integration)
  - [Creating a Discord Bot](#creating-a-discord-bot)
  - [Getting the Required Credentials](#getting-the-discord-credentials)
  - [Configuration](#discord-configuration)
- [Using the Notifiers](#using-the-notifiers)

## Overview

Notte provides notification services that can send task results to both Slack and Discord. Each integration requires specific credentials that you'll need to obtain from their respective platforms.

## Slack Integration

### Creating a Slack App

1. Go to [Slack API](https://api.slack.com/apps)
2. Click "Create New App"
3. Select "From scratch"
4. Enter a name for your app (e.g., "Notte Notifier")
5. Select the workspace where you want to install the app
6. Click "Create App"

### Getting the Slack Credentials

1. In your app's settings page, navigate to "OAuth & Permissions" in the sidebar
2. Scroll down to "Scopes" and add the following Bot Token Scopes:
   - `chat:write`
   - `chat:write.public`
3. Scroll back to the top and click "Install to Workspace"
4. Authorize the app installation
5. After installation, you'll see a "Bot User OAuth Token" that starts with `xoxb-` - copy this token

To get your channel ID:
1. Open Slack in your browser
2. Navigate to the channel where you want to send notifications
3. The channel ID is in the URL: `https://app.slack.com/client/TXXXXXXXX/CXXXXXXXXX`
   (The `CXXXXXXXXX` part is your channel ID)

### Slack Configuration

Use the following code to initialize the Slack notifier:

```python
from notte_core.notifiers.slack import SlackNotifier

slack_notifier = SlackNotifier(
    token="xoxb-your-token-here",
    channel_id="C0123456789"
)
```

## Discord Integration

### Creating a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Enter a name for your app (e.g., "Notte Notifier")
4. Navigate to the "Bot" tab in the left sidebar
5. Click "Add Bot"
6. Under the "Privileged Gateway Intents" section, enable "Message Content Intent"

### Getting the Discord Credentials

To get your bot token:
1. In the "Bot" tab, click "Reset Token" to generate a new token
2. Copy the token - this is your bot token

To invite the bot to your server:
1. Go to the "OAuth2" tab and then "URL Generator"
2. Select the following scopes:
   - `bot`
3. Select the following bot permissions:
   - "Send Messages"
   - "Read Message History"
4. Copy the generated URL and open it in your browser
5. Select the server you want to add the bot to and authorize

To get your channel ID:
1. In Discord, enable Developer Mode (User Settings > Advanced > Developer Mode)
2. Right-click on the channel you want to send messages to
3. Select "Copy ID"

### Discord Configuration

Use the following code to initialize the Discord notifier:

```python
from notte_core.notifiers.discord import DiscordNotifier


discord_notifier = DiscordNotifier(
    token="your-discord-bot-token-here",
    channel_id=123456789012345678
)
```

## Using the Notifiers

Once configured, you can use the notifiers to send notifications:

```python
from notte_core.common.agent.types import AgentResponse

# Create a sample response
response = AgentResponse(answer="This is a test notification")

# Send notifications
await slack_notifier.notify("Test Task", response)
await discord_notifier.notify("Test Task", response)
```

The notifications will be formatted according to each platform's markdown styles:
- Slack uses `*text*` for bold
- Discord uses `**text**` for bold

Remember that both notifiers require async functions, so they must be called within an async context.
