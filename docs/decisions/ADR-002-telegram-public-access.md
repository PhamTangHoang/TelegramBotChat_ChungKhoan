# ADR-002: Explicit Telegram public access mode

## Status

Accepted

## Context

The bot was initially designed for a private whitelist. The owner also needs an
option for any Telegram user or group to run the same deterministic analysis.
An empty whitelist alone is ambiguous and could accidentally expose the bot.

## Decision

Add `TELEGRAM_PUBLIC_ACCESS`, defaulting to `false`. When set to `true`, the
access controller allows every chat and still applies the existing per-chat rate
limit. When it is `false`, only `TELEGRAM_ALLOWED_CHAT_IDS` may use the bot.

## Consequences

Public mode is easy to enable and cannot be confused with an accidentally empty
allowlist. It may increase provider, database and Gemini usage, so deployment
owners should set appropriate rate limits and quotas.
