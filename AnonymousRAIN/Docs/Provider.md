# Provider Interface

The project uses an `ILlmProvider` abstraction for chat completion backends. Provider implementations translate internal messages to a backend-specific HTTP API and return normalized text, tool calls, and usage.
