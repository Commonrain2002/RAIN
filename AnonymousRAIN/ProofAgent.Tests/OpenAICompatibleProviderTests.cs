using System.Reflection;
using System.Text.Json;
using ProofAgent.Llm;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class OpenAICompatibleProviderTests
{
    [Fact]
    public void ParseChatCompletionJsonForTests_ReadsUsage()
    {
        const string json = """
            {
              "choices":[{"message":{"role":"assistant","content":"hi"}}],
              "usage":{"prompt_tokens":100,"completion_tokens":20,"total_tokens":120}
            }
            """;

        var r = _InvokeFromOpenAICompatibleResponseViaReflection(json);

        Assert.Equal("hi", r.Text);
        Assert.Equal(100, r.Usage.PromptTokens);
        Assert.Equal(20, r.Usage.CompletionTokens);
        Assert.Equal(120, r.Usage.TotalTokens);
    }

    [Fact]
    public void ParseChatCompletionJsonForTests_MissingUsage_IsZero()
    {
        const string json = """{"choices":[{"message":{"role":"assistant","content":"x"}}]}""";

        var r = _InvokeFromOpenAICompatibleResponseViaReflection(json);

        Assert.Equal(LlmUsage.Zero, r.Usage);
    }

    [Fact]
    public void ParseChatCompletionJsonForTests_OmittedTotalTokens_DerivesFromPromptAndCompletion()
    {
        const string json = """
            {
              "choices":[{"message":{"role":"assistant","content":""}}],
              "usage":{"prompt_tokens":7,"completion_tokens":3}
            }
            """;

        var r = _InvokeFromOpenAICompatibleResponseViaReflection(json);

        Assert.Equal(7, r.Usage.PromptTokens);
        Assert.Equal(3, r.Usage.CompletionTokens);
        Assert.Equal(10, r.Usage.TotalTokens);
    }

    [Fact]
    public void ParseChatCompletionJsonForTests_ReadsPromptCacheHitAndMissTokens()
    {
        const string json = """
            {
              "choices":[{"message":{"role":"assistant","content":"hi"}}],
              "usage":{
                "prompt_tokens":100,
                "completion_tokens":20,
                "total_tokens":120,
                "prompt_cache_hit_tokens":80,
                "prompt_cache_miss_tokens":20
              }
            }
            """;

        var r = _InvokeFromOpenAICompatibleResponseViaReflection(json);

        Assert.Equal(80, r.Usage.PromptCacheHitTokens);
        Assert.Equal(20, r.Usage.PromptCacheMissTokens);
    }

    [Fact]
    public void ParseChatCompletionJsonForTests_ReadsPromptCacheHitFromPromptTokensDetailsCachedTokens()
    {
        const string json = """
            {
              "choices":[{"message":{"role":"assistant","content":"hi"}}],
              "usage":{
                "prompt_tokens":2006,
                "completion_tokens":300,
                "total_tokens":2306,
                "prompt_tokens_details":{"cached_tokens":1920}
              }
            }
            """;

        var r = _InvokeFromOpenAICompatibleResponseViaReflection(json);

        Assert.Equal(2006, r.Usage.PromptTokens);
        Assert.Equal(300, r.Usage.CompletionTokens);
        Assert.Equal(1920, r.Usage.PromptCacheHitTokens);
        Assert.Equal(0, r.Usage.PromptCacheMissTokens);
    }

    [Fact]
    public void BuildRequestExtraBodyRoot_WritesThinkingTypeAndReasoningEffort()
    {
        var extra = _InvokeBuildRequestExtraBodyRootViaReflection(new LlmChatOptions(true, "max"));
        using var doc = JsonDocument.Parse(extra.GetRawText());
        var thinking = doc.RootElement.GetProperty("thinking");
        Assert.Equal("enabled", thinking.GetProperty("type").GetString());
        Assert.Equal("max", thinking.GetProperty("reasoning_effort").GetString());
        var reasoning = doc.RootElement.GetProperty("reasoning");
        Assert.Equal("max", reasoning.GetProperty("effort").GetString());
        Assert.Equal("auto", reasoning.GetProperty("summary").GetString());
    }

    [Fact]
    public void BuildRequestExtraBodyRoot_DisabledThinking_UsesDisabledType()
    {
        var extra = _InvokeBuildRequestExtraBodyRootViaReflection(new LlmChatOptions(false, "high"));
        using var doc = JsonDocument.Parse(extra.GetRawText());
        var thinking = doc.RootElement.GetProperty("thinking");
        Assert.Equal("disabled", thinking.GetProperty("type").GetString());
        Assert.Equal("high", thinking.GetProperty("reasoning_effort").GetString());
        Assert.False(doc.RootElement.TryGetProperty("reasoning", out _));
    }

    [Fact]
    public void ParseChatCompletionJsonForTests_ReadsReasoningSummaryFromResponsesOutput()
    {
        const string json = """
            {
              "output":[
                {
                  "type":"reasoning",
                  "summary":[{"type":"summary_text","text":"Plan: unfold then extlia."}]
                },
                {
                  "type":"message",
                  "content":[{"type":"output_text","text":"done"}]
                }
              ],
              "usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}
            }
            """;

        var r = _InvokeFromOpenAICompatibleResponseViaReflection(json);

        Assert.Equal("", r.Text);
        Assert.Equal("Plan: unfold then extlia.", r.ReasoningSummaryText);
    }

    [Fact]
    public void ParseChatCompletionJsonForTests_ReadsReasoningContentAndSummaryOnMessage()
    {
        const string json = """
            {
              "choices":[{
                "message":{
                  "role":"assistant",
                  "content":"ok",
                  "reasoning_content":"full chain",
                  "reasoning":{"summary":[{"text":"short summary"}]}
                }
              }],
              "usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}
            }
            """;

        var r = _InvokeFromOpenAICompatibleResponseViaReflection(json);

        Assert.Equal("ok", r.Text);
        Assert.Equal("full chain", r.ReasoningText);
        Assert.Equal("short summary", r.ReasoningSummaryText);
    }

    [Fact]
    public void BuildChatCompletionRequestJsonForTests_IncludesReasoningContentOnAssistantTurn()
    {
        var extra = _InvokeBuildRequestExtraBodyRootViaReflection(new LlmChatOptions(true, "high"));
        var messages = new LlmMessage[]
        {
            LlmMessage.CreateUser("u"),
            LlmMessage.CreateAssistant("", new[] { new ToolCall("id1", "fn", "{}") }, "chain-of-thought"),
            LlmMessage.CreateTool("id1", "tool output")
        };

        var json = ReflectionTestAccess.InvokeStaticNonPublic<string>(
            typeof(OpenAICompatibleProvider),
            "_BuildRequestJson",
            new object?[]
            {
                "deepseek-v4-flash",
                messages,
                Array.Empty<JsonElement>(),
                extra
            });
        Assert.NotNull(json);

        using var parsed = JsonDocument.Parse(json);
        var msgs = parsed.RootElement.GetProperty("messages");
        Assert.Equal(JsonValueKind.String, msgs[1].GetProperty("reasoning_content").ValueKind);
        Assert.Equal("chain-of-thought", msgs[1].GetProperty("reasoning_content").GetString());
        Assert.Equal("enabled", parsed.RootElement.GetProperty("thinking").GetProperty("type").GetString());
        Assert.Equal("high", parsed.RootElement.GetProperty("thinking").GetProperty("reasoning_effort").GetString());
    }

    [Fact]
    public void BuildChatCompletionRequestJsonForTests_OmitsExtraWhenNull()
    {
        var messages = new[] { LlmMessage.CreateUser("hi") };
        var json = ReflectionTestAccess.InvokeStaticNonPublic<string>(
            typeof(OpenAICompatibleProvider),
            "_BuildRequestJson",
            new object?[]
            {
                "m",
                messages,
                Array.Empty<JsonElement>(),
                null
            });
        Assert.NotNull(json);

        using var parsed = JsonDocument.Parse(json);
        Assert.False(parsed.RootElement.TryGetProperty("thinking", out _));
    }

    #region Private Methods

    private static JsonElement _InvokeBuildRequestExtraBodyRootViaReflection(LlmChatOptions chatOptions)
    {
        var method = typeof(OpenAICompatibleProvider).GetMethod(
            "_BuildRequestExtraBodyRoot",
            BindingFlags.Static | BindingFlags.NonPublic);
        Assert.NotNull(method);
        var raw = method.Invoke(null, new object[] { chatOptions });
        Assert.NotNull(raw);
        return (JsonElement)raw;
    }

    private static LlmResponse _InvokeFromOpenAICompatibleResponseViaReflection(string json)
    {
        var logger = TestInjectedLogger.CreateFatalOnly();
        var llmHttpClient = new HttpClient();
        var provider = new OpenAICompatibleProvider(
            llmHttpClient,
            "test-model",
            new Uri("https://example.invalid/"),
            "test-key",
            logger);
        var method = typeof(OpenAICompatibleProvider).GetMethod(
            "_FromResponse",
            BindingFlags.Instance | BindingFlags.NonPublic);
        Assert.NotNull(method);
        var result = method.Invoke(provider, new object[] { json });
        Assert.NotNull(result);
        return (LlmResponse)result;
    }

    #endregion Private Methods
}
