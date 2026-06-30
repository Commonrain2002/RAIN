using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Serilog;

namespace ProofAgent.Llm;

/// <summary>
/// Chat completions via OpenAI-compatible HTTP (e.g. DeepSeek); tool declarations as function JSON.
/// The caller supplies the full chat completions POST <c>Uri</c> (no path suffix is appended) and the chat <c>model</c> id; may merge vendor request fields via <c>JsonElement</c> (e.g. DeepSeek <c>thinking</c> with <c>type</c> and <c>reasoning_effort</c>).
/// A shared <see cref="HttpClient"/> is safe for concurrent <see cref="HttpClient.PostAsync"/> when authorization and timeout are set once in the constructor;
/// do not mutate <see cref="HttpClient.DefaultRequestHeaders"/> or <see cref="HttpClient.Timeout"/> on a shared instance afterward.
/// Concurrent <see cref="ChatAsync"/> on the same provider instance is not assumed by current callers (serial sessions).
/// </summary>
public class OpenAICompatibleProvider : ILlmProvider
{
    #region Fields

    private readonly HttpClient _Http;

    private readonly string _Model;

    private readonly Uri _Endpoint;

    private readonly ILogger _Logger;

    #endregion Fields

    public OpenAICompatibleProvider(
        HttpClient httpClient,
        string model,
        Uri endpoint,
        string apiKey,
        ILogger logger,
        TimeSpan? httpTimeout = null)
    {
        _Http = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
        _Model = model;
        _Endpoint = endpoint;
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        if (httpTimeout.HasValue)
        {
            _Http.Timeout = httpTimeout.Value;
        }

        _Http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
    }

    public async Task<LlmResponse> ChatAsync(
        IReadOnlyList<LlmMessage> messages,
        IReadOnlyList<JsonElement> toolDeclarations,
        LlmChatOptions chatOptions,
        CancellationToken cancellationToken)
    {
        var extraRoot = _BuildRequestExtraBodyRoot(chatOptions);
        var requestJson = _BuildRequestJson(_Model, messages, toolDeclarations, extraRoot);
        _LogOutgoingChatCompletionConfig(requestJson);
        using var content = new StringContent(requestJson, Encoding.UTF8, "application/json");
        using var resp = await _Http.PostAsync(_Endpoint, content, cancellationToken).ConfigureAwait(false);
        var body = await resp.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"LLM request failed: {(int)resp.StatusCode} {resp.ReasonPhrase}\n{body}");
        }

        return _FromResponse(body);
    }

    #region Private Methods

    private static JsonElement _BuildRequestExtraBodyRoot(LlmChatOptions chatOptions)
    {
        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            writer.WritePropertyName("thinking");
            writer.WriteStartObject();
            writer.WriteString("type", chatOptions.EnableReasoning ? "enabled" : "disabled");
            writer.WriteBoolean("enable_thinking", chatOptions.EnableReasoning);
            writer.WriteString("reasoning_effort", chatOptions.ReasoningEffort);
            writer.WriteEndObject();
            if (chatOptions.EnableReasoning)
            {
                writer.WritePropertyName("reasoning");
                writer.WriteStartObject();
                writer.WriteString("effort", chatOptions.ReasoningEffort);
                if (!string.IsNullOrEmpty(chatOptions.ReasoningSummary))
                {
                    writer.WriteString("summary", chatOptions.ReasoningSummary);
                }
                writer.WriteEndObject();
            }

            writer.WriteEndObject();
        }

        using var doc = JsonDocument.Parse(buffer.ToArray());
        return doc.RootElement.Clone();
    }

    private static string _BuildRequestJson(
        string model,
        IReadOnlyList<LlmMessage> messages,
        IReadOnlyList<JsonElement> toolDeclarations,
        JsonElement? llmRequestExtraBodyRoot)
    {
        var msgArray = new List<object>();
        foreach (var m in messages)
        {
            switch (m.Role)
            {
                case LlmParticipantRole.System:
                    msgArray.Add(new Dictionary<string, object?>
                    {
                        ["role"] = "system",
                        ["content"] = m.Content
                    });
                    break;
                case LlmParticipantRole.User:
                    msgArray.Add(new Dictionary<string, object?>
                    {
                        ["role"] = "user",
                        ["content"] = m.Content
                    });
                    break;
                case LlmParticipantRole.Tool:
                    msgArray.Add(new Dictionary<string, object?>
                    {
                        ["role"] = "tool",
                        ["tool_call_id"] = m.ToolCallID,
                        ["content"] = m.Content
                    });
                    break;
                case LlmParticipantRole.Assistant:
                    _AppendAssistantMessageForRequest(msgArray, m);
                    break;
                default:
                    throw new ArgumentOutOfRangeException(nameof(m.Role), m.Role, null);
            }
        }

        var root = new Dictionary<string, object?>
        {
            ["model"] = model,
            ["messages"] = msgArray
        };

        if (toolDeclarations.Count > 0)
        {
            // toolDeclarations are already {name,description,parameters} JSON; pass through as tools list
            var tools = toolDeclarations
                .Select(static d => new Dictionary<string, object?>
                {
                    ["type"] = "function",
                    ["function"] = JsonSerializer.Deserialize<JsonElement>(d.GetRawText())
                })
                .ToList();
            root["tools"] = tools;
            root["tool_choice"] = "auto";
        }

        return _SerializeRootWithMergedExtra(root, llmRequestExtraBodyRoot);
    }

    private void _LogOutgoingChatCompletionConfig(string requestJson)
    {
        using var doc = JsonDocument.Parse(requestJson);
        var root = doc.RootElement;
        var model = root.TryGetProperty("model", out var modelEl) && modelEl.ValueKind == JsonValueKind.String
            ? modelEl.GetString() ?? _Model
            : _Model;
        var reasoningEffort = "(not set)";
        if (root.TryGetProperty("thinking", out var thinkingEl) &&
            thinkingEl.ValueKind == JsonValueKind.Object &&
            thinkingEl.TryGetProperty("reasoning_effort", out var effortEl) &&
            effortEl.ValueKind == JsonValueKind.String)
        {
            var effort = effortEl.GetString();
            if (!string.IsNullOrWhiteSpace(effort))
            {
                reasoningEffort = effort;
            }
        }

        var reasoningSummary = "(not set)";
        if (root.TryGetProperty("reasoning", out var reasoningEl) &&
            reasoningEl.ValueKind == JsonValueKind.Object &&
            reasoningEl.TryGetProperty("summary", out var summaryEl) &&
            summaryEl.ValueKind == JsonValueKind.String)
        {
            var summary = summaryEl.GetString();
            if (!string.IsNullOrWhiteSpace(summary))
            {
                reasoningSummary = summary;
            }
        }

        _Logger.Information(
            "LLM request config: model={Model} reasoning_effort={ReasoningEffort} reasoning_summary={ReasoningSummary}",
            model,
            reasoningEffort,
            reasoningSummary);
    }

    private static void _AppendAssistantMessageForRequest(List<object> msgArray, LlmMessage m)
    {
        if (m.AssistantToolCalls is { Count: > 0 } calls)
        {
            var mappedCalls = calls.Select(static c => new Dictionary<string, object?>
            {
                ["id"] = c.ToolCallID,
                ["type"] = "function",
                ["function"] = new Dictionary<string, object?>
                {
                    ["name"] = c.Name,
                    ["arguments"] = string.IsNullOrWhiteSpace(c.Arguments) ? "{}" : c.Arguments
                }
            }).ToList();

            var withTools = new Dictionary<string, object?>
            {
                ["role"] = "assistant",
                ["content"] = m.Content,
                ["tool_calls"] = mappedCalls
            };
            _AddReasoningContentIfPresent(withTools, m);
            msgArray.Add(withTools);
            return;
        }

        var textOnly = new Dictionary<string, object?>
        {
            ["role"] = "assistant",
            ["content"] = m.Content
        };
        _AddReasoningContentIfPresent(textOnly, m);
        msgArray.Add(textOnly);
    }

    private static void _AddReasoningContentIfPresent(Dictionary<string, object?> assistantObject, LlmMessage m)
    {
        if (!string.IsNullOrEmpty(m.AssistantReasoningContent))
        {
            assistantObject["reasoning_content"] = m.AssistantReasoningContent;
        }
    }

    private static string _SerializeRootWithMergedExtra(
        Dictionary<string, object?> root,
        JsonElement? llmRequestExtraBodyRoot)
    {
        var serialized = JsonSerializer.Serialize(root);
        if (!llmRequestExtraBodyRoot.HasValue || llmRequestExtraBodyRoot.Value.ValueKind != JsonValueKind.Object)
        {
            return serialized;
        }

        var rootObj = JsonNode.Parse(serialized)!.AsObject();
        var extraObj = JsonNode.Parse(llmRequestExtraBodyRoot.Value.GetRawText())!.AsObject();
        foreach (var kvp in extraObj)
        {
            rootObj[kvp.Key] = kvp.Value?.DeepClone();
        }

        return rootObj.ToJsonString();
    }

    private LlmResponse _FromResponse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        var text = "";
        string? reasoning = null;
        string? reasoningSummary = null;
        var toolCalls = new List<ToolCall>();
        if (_TryGetFirstChoiceMessage(root, out var message))
        {
            text = _ParseMessageContent(message);
            reasoning = _ParseMessageReasoning(message);
            reasoningSummary = _ParseMessageReasoningSummary(message);
            toolCalls = _ParseMessageToolCalls(message);
        }

        if (string.IsNullOrWhiteSpace(reasoningSummary))
        {
            reasoningSummary = _ParseResponsesReasoningSummary(root);
        }

        var usage = _ParseUsage(root);
        return new LlmResponse(text, toolCalls, reasoning, usage, reasoningSummary);
    }

    private static bool _TryGetFirstChoiceMessage(JsonElement root, out JsonElement message)
    {
        message = default;
        if (!root.TryGetProperty("choices", out var choices) ||
            choices.ValueKind != JsonValueKind.Array ||
            choices.GetArrayLength() == 0)
        {
            return false;
        }

        var choice0 = choices[0];
        if (!choice0.TryGetProperty("message", out message) || message.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        return true;
    }

    private static string _ParseMessageContent(JsonElement message)
    {
        if (!message.TryGetProperty("content", out var contentEl))
        {
            return "";
        }

        return contentEl.ValueKind == JsonValueKind.String ? (contentEl.GetString() ?? "") : "";
    }

    private static string? _ParseMessageReasoning(JsonElement message)
    {
        if (message.TryGetProperty("reasoning_content", out var reasoningContent) &&
            reasoningContent.ValueKind == JsonValueKind.String)
        {
            return reasoningContent.GetString();
        }

        if (message.TryGetProperty("reasoning", out var reasoningEl) && reasoningEl.ValueKind == JsonValueKind.String)
        {
            return reasoningEl.GetString();
        }

        return null;
    }

    private static string? _ParseMessageReasoningSummary(JsonElement message)
    {
        if (!message.TryGetProperty("reasoning", out var reasoningEl) || reasoningEl.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        return _ParseReasoningObjectSummaryText(reasoningEl);
    }

    private static string? _ParseResponsesReasoningSummary(JsonElement root)
    {
        if (!root.TryGetProperty("output", out var outputEl) || outputEl.ValueKind != JsonValueKind.Array)
        {
            return null;
        }

        var parts = new List<string>();
        foreach (var item in outputEl.EnumerateArray())
        {
            if (!item.TryGetProperty("type", out var typeEl) || typeEl.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            if (!string.Equals(typeEl.GetString(), "reasoning", StringComparison.Ordinal))
            {
                continue;
            }

            var segment = _ParseReasoningOutputItemSummaryText(item);
            if (!string.IsNullOrWhiteSpace(segment))
            {
                parts.Add(segment);
            }
        }

        if (parts.Count == 0)
        {
            return null;
        }

        return string.Join("\n\n", parts);
    }

    private static string? _ParseReasoningOutputItemSummaryText(JsonElement reasoningItem)
    {
        if (reasoningItem.TryGetProperty("summary", out var summaryEl))
        {
            var fromSummaryArray = _ParseSummaryArrayText(summaryEl);
            if (!string.IsNullOrWhiteSpace(fromSummaryArray))
            {
                return fromSummaryArray;
            }
        }

        return _ParseReasoningObjectSummaryText(reasoningItem);
    }

    private static string? _ParseReasoningObjectSummaryText(JsonElement reasoningObject)
    {
        if (reasoningObject.TryGetProperty("summary", out var summaryEl))
        {
            var fromSummaryArray = _ParseSummaryArrayText(summaryEl);
            if (!string.IsNullOrWhiteSpace(fromSummaryArray))
            {
                return fromSummaryArray;
            }
        }

        if (reasoningObject.TryGetProperty("summary_text", out var summaryTextEl) &&
            summaryTextEl.ValueKind == JsonValueKind.String)
        {
            return summaryTextEl.GetString();
        }

        return null;
    }

    private static string? _ParseSummaryArrayText(JsonElement summaryEl)
    {
        if (summaryEl.ValueKind == JsonValueKind.String)
        {
            return summaryEl.GetString();
        }

        if (summaryEl.ValueKind != JsonValueKind.Array)
        {
            return null;
        }

        var parts = new List<string>();
        foreach (var entry in summaryEl.EnumerateArray())
        {
            if (entry.ValueKind == JsonValueKind.String)
            {
                var s = entry.GetString();
                if (!string.IsNullOrWhiteSpace(s))
                {
                    parts.Add(s);
                }

                continue;
            }

            if (entry.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            if (entry.TryGetProperty("text", out var textEl) && textEl.ValueKind == JsonValueKind.String)
            {
                var t = textEl.GetString();
                if (!string.IsNullOrWhiteSpace(t))
                {
                    parts.Add(t);
                }
            }
        }

        if (parts.Count == 0)
        {
            return null;
        }

        return string.Join("\n\n", parts);
    }

    private static List<ToolCall> _ParseMessageToolCalls(JsonElement message)
    {
        var mapped = new List<ToolCall>();
        if (!message.TryGetProperty("tool_calls", out var toolCallsEl) || toolCallsEl.ValueKind != JsonValueKind.Array)
        {
            return mapped;
        }

        foreach (var tc in toolCallsEl.EnumerateArray())
        {
            if (_TryParseToolCallElement(tc, out var toolCall) && toolCall != null)
            {
                mapped.Add(toolCall);
            }
        }

        return mapped;
    }

    private static bool _TryParseToolCallElement(JsonElement toolCallElement, out ToolCall? toolCall)
    {
        toolCall = null;
        if (toolCallElement.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        var id = toolCallElement.TryGetProperty("id", out var idEl) && idEl.ValueKind == JsonValueKind.String
            ? (idEl.GetString() ?? "")
            : "";

        if (!toolCallElement.TryGetProperty("function", out var fn) || fn.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        var name = fn.TryGetProperty("name", out var nameEl) && nameEl.ValueKind == JsonValueKind.String
            ? (nameEl.GetString() ?? "")
            : "";

        if (string.IsNullOrWhiteSpace(name))
        {
            return false;
        }

        var args = fn.TryGetProperty("arguments", out var argsEl)
            ? (argsEl.ValueKind == JsonValueKind.String ? (argsEl.GetString() ?? "{}") : argsEl.GetRawText())
            : "{}";

        toolCall = new ToolCall(id, name, args);
        return true;
    }

    private LlmUsage _ParseUsage(JsonElement root)
    {
        if (!root.TryGetProperty("usage", out var usageEl) || usageEl.ValueKind != JsonValueKind.Object)
        {
            _Logger.Debug("OpenAICompatibleProvider: no usage object in response; token counts default to 0.");
            return LlmUsage.Zero;
        }

        var prompt = _ReadNonNegativeInt(usageEl, "prompt_tokens");
        var completion = _ReadNonNegativeInt(usageEl, "completion_tokens");
        var total = _ReadNonNegativeInt(usageEl, "total_tokens");
        var promptCacheHit = _ReadPromptCacheHitTokens(usageEl);
        var promptCacheMiss = _ReadNonNegativeInt(usageEl, "prompt_cache_miss_tokens");
        if (total == 0 && (prompt != 0 || completion != 0))
        {
            total = prompt + completion;
        }

        return new LlmUsage(prompt, completion, total, promptCacheHit, promptCacheMiss);
    }

    private static int _ReadNonNegativeInt(JsonElement obj, string name)
    {
        if (!obj.TryGetProperty(name, out var el) || el.ValueKind != JsonValueKind.Number)
        {
            return 0;
        }

        return el.TryGetInt32(out var i) ? Math.Max(0, i) : 0;
    }

    private static int _ReadPromptCacheHitTokens(JsonElement usageElement)
    {
        if (usageElement.TryGetProperty("prompt_cache_hit_tokens", out var hitElement) && hitElement.ValueKind == JsonValueKind.Number)
        {
            return hitElement.TryGetInt32(out var hit) ? Math.Max(0, hit) : 0;
        }

        if (usageElement.TryGetProperty("prompt_tokens_details", out var detailsElement)
            && detailsElement.ValueKind == JsonValueKind.Object
            && detailsElement.TryGetProperty("cached_tokens", out var cachedElement)
            && cachedElement.ValueKind == JsonValueKind.Number)
        {
            return cachedElement.TryGetInt32(out var cached) ? Math.Max(0, cached) : 0;
        }

        return 0;
    }

    #endregion Private Methods
}
