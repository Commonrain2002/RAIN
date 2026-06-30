namespace ProofAgent.Llm;

/// <summary>Token usage from an OpenAI-compatible API (single completion).</summary>
public readonly struct LlmUsage : IEquatable<LlmUsage>
{
    public static LlmUsage Zero { get; } = new(0, 0, 0, 0, 0);

    public int PromptTokens { get; }

    public int CompletionTokens { get; }

    public int TotalTokens { get; }

    /// <summary>Prompt tokens served from context cache (<c>prompt_cache_hit_tokens</c>, or <c>prompt_tokens_details.cached_tokens</c>).</summary>
    public int PromptCacheHitTokens { get; }

    /// <summary>Prompt tokens not served from context cache (OpenAI-compatible <c>prompt_cache_miss_tokens</c>).</summary>
    public int PromptCacheMissTokens { get; }

    public LlmUsage(
        int promptTokens,
        int completionTokens,
        int totalTokens,
        int promptCacheHitTokens = 0,
        int promptCacheMissTokens = 0)
    {
        PromptTokens = promptTokens;
        CompletionTokens = completionTokens;
        TotalTokens = totalTokens;
        PromptCacheHitTokens = promptCacheHitTokens;
        PromptCacheMissTokens = promptCacheMissTokens;
    }

    /// <summary>Add component-wise; returns new usage (immutable value type).</summary>
    public LlmUsage Add(LlmUsage other)
    {
        return new LlmUsage(
            PromptTokens + other.PromptTokens,
            CompletionTokens + other.CompletionTokens,
            TotalTokens + other.TotalTokens,
            PromptCacheHitTokens + other.PromptCacheHitTokens,
            PromptCacheMissTokens + other.PromptCacheMissTokens);
    }

    public bool Equals(LlmUsage other)
    {
        return PromptTokens == other.PromptTokens
            && CompletionTokens == other.CompletionTokens
            && TotalTokens == other.TotalTokens
            && PromptCacheHitTokens == other.PromptCacheHitTokens
            && PromptCacheMissTokens == other.PromptCacheMissTokens;
    }

    public override bool Equals(object? obj)
    {
        return obj is LlmUsage other && Equals(other);
    }

    public override int GetHashCode()
    {
        return HashCode.Combine(
            PromptTokens,
            CompletionTokens,
            TotalTokens,
            PromptCacheHitTokens,
            PromptCacheMissTokens);
    }
}
